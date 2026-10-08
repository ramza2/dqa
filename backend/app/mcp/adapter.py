"""Application-service adapter boundary for MCP tools.

MCP transport handlers and tools call this facade only. It must not open DEMIS
connections, execute SQL, or import Catalog packages. Discovery tools (28-B)
delegate into existing DQA application services from here. Query tools (28-C)
are out of scope.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryError
from app.adapters.data_discovery.errors import DataDiscoveryError
from app.adapters.db.session import get_session_factory
from app.adapters.embedding.factory import create_embedding_provider
from app.auth.errors import AuthError, AuthErrorCode
from app.auth.models import AuthenticatedActor, Permission
from app.auth.rbac import actor_has_permission
from app.core.config import Settings, get_settings
from app.domain.data_discovery import DataDiscoverySearchMode
from app.mcp.errors import (
    raise_catalog_revision_changed,
    raise_from_discovery_or_catalog_error,
    raise_invalid_tool_arguments,
)
from app.schemas.data_discovery import DataDiscoverySearchRequest
from app.services.catalog_query import (
    PageResult,
    ResolvedActiveRevision,
    get_table,
    list_columns,
    list_indexes,
    list_relations,
)
from app.services.data_discovery_search import search_schema

# Bound for describe_resource metadata collections (columns / relations / indexes).
_DESCRIBE_COLLECTION_LIMIT = 500


def _assert_same_active_revision(
    expected: ResolvedActiveRevision,
    actual: ResolvedActiveRevision,
) -> None:
    """Fail closed when active revision identity drifts across metadata reads."""
    if (
        actual.revision_id != expected.revision_id
        or actual.schema_fingerprint != expected.schema_fingerprint
        or actual.source_name != expected.source_name
    ):
        raise_catalog_revision_changed()


def _bounded_collection(page: PageResult, *, limit: int) -> dict[str, Any]:
    """Serialize a page with explicit truncation metadata (never silent)."""
    items = [item.model_dump(mode="json") for item in page.items]
    returned = len(items)
    return {
        "items": items,
        "total": page.total,
        "returned": returned,
        "limit": limit,
        "truncated": page.total > returned,
    }


class McpApplicationAdapter:
    """Facade used by MCP tools — reuses application services, never HTTP loopback."""

    def readiness(self, actor: AuthenticatedActor) -> dict[str, Any]:
        """Return MCP foundation readiness (no DB / DEMIS / LLM I/O)."""
        return {
            "status": "ready",
            "phase": "28-B",
            "client": "MCP",
            "actor_id": actor.actor_id,
            "provider": actor.provider,
        }

    def require_catalog_read(self, actor: AuthenticatedActor) -> None:
        """Enforce CATALOG_READ at the tool/service boundary (defense in depth)."""
        if not actor_has_permission(actor, Permission.CATALOG_READ):
            raise AuthError(
                AuthErrorCode.AUTHORIZATION_DENIED,
                "permission denied",
            )

    def search_schema(
        self,
        actor: AuthenticatedActor,
        *,
        source_name: str,
        query: str,
        mode: str = "keyword",
        object_type: str | None = None,
        top_k: int = 10,
        expand_terms: bool = False,
        expand_relations: bool = False,
        max_relation_hops: int = 0,
        settings: Settings | None = None,
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Search active Catalog schema metadata (keyword / semantic / hybrid)."""
        self.require_catalog_read(actor)
        try:
            request = DataDiscoverySearchRequest(
                source_name=source_name,
                query=query,
                mode=mode,
                object_type=object_type,
                top_k=top_k,
                expand_terms=expand_terms,
                expand_relations=expand_relations,
                max_relation_hops=max_relation_hops,
            )
        except (ValidationError, ValueError, TypeError):
            raise_invalid_tool_arguments()

        cfg = settings or get_settings()
        owns_session = session is None
        db = session or get_session_factory()()
        provider = None
        try:
            search_mode = (
                request.mode
                if isinstance(request.mode, DataDiscoverySearchMode)
                else DataDiscoverySearchMode(str(request.mode))
            )
            if search_mode in {
                DataDiscoverySearchMode.SEMANTIC,
                DataDiscoverySearchMode.HYBRID,
            }:
                provider = create_embedding_provider(cfg)
            response = search_schema(
                db,
                request,
                embedding_provider=provider,
                settings=cfg,
            )
            return response.model_dump(mode="json")
        except (DataDiscoveryError, CatalogQueryError) as exc:
            raise_from_discovery_or_catalog_error(exc)
        finally:
            if provider is not None:
                provider.close()
            if owns_session:
                db.close()

    def describe_resource(
        self,
        actor: AuthenticatedActor,
        *,
        source_name: str,
        schema_name: str,
        table_name: str,
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Return Catalog-derived table/column/PK/FK/index metadata for one table.

        Does not invent logical clinical mappings or executable field capabilities
        (Phase 29). Active Catalog revision only.
        """
        self.require_catalog_read(actor)
        source = (source_name or "").strip()
        schema = (schema_name or "").strip()
        table = (table_name or "").strip()
        if not source or not schema or not table:
            raise_invalid_tool_arguments()
        if len(source) > 255 or len(schema) > 255 or len(table) > 255:
            raise_invalid_tool_arguments()

        owns_session = session is None
        db = session or get_session_factory()()
        limit = _DESCRIBE_COLLECTION_LIMIT
        try:
            # Each catalog_query helper re-resolves the active pointer. Anchor on
            # the table snapshot, then fail closed if later pages disagree.
            resolved, table_detail = get_table(db, source, schema, table)

            columns_resolved, columns_page = list_columns(
                db,
                source,
                schema_name=schema,
                table_name=table,
                limit=limit,
                offset=0,
            )
            _assert_same_active_revision(resolved, columns_resolved)

            relations_resolved, relations_page = list_relations(
                db,
                source,
                schema_name=schema,
                table_name=table,
                limit=limit,
                offset=0,
            )
            _assert_same_active_revision(resolved, relations_resolved)

            indexes_resolved, indexes_page = list_indexes(
                db,
                source,
                schema_name=schema,
                table_name=table,
                limit=limit,
                offset=0,
            )
            _assert_same_active_revision(resolved, indexes_resolved)

            # Separate PK page so primary keys remain complete even when the
            # general columns page is truncated (unless there are >limit PKs).
            pk_resolved, pk_page = list_columns(
                db,
                source,
                schema_name=schema,
                table_name=table,
                is_primary_key=True,
                limit=limit,
                offset=0,
            )
            _assert_same_active_revision(resolved, pk_resolved)

            return {
                "source_name": resolved.source_name,
                "revision_id": resolved.revision_id,
                "schema_fingerprint": resolved.schema_fingerprint,
                "table": table_detail.model_dump(mode="json"),
                "columns": _bounded_collection(columns_page, limit=limit),
                "primary_key_columns": _bounded_collection(pk_page, limit=limit),
                "relations": _bounded_collection(relations_page, limit=limit),
                "indexes": _bounded_collection(indexes_page, limit=limit),
            }
        except CatalogQueryError as exc:
            raise_from_discovery_or_catalog_error(exc)
        finally:
            if owns_session:
                db.close()


def get_mcp_application_adapter() -> McpApplicationAdapter:
    return McpApplicationAdapter()
