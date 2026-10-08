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
    raise_from_discovery_or_catalog_error,
    raise_invalid_tool_arguments,
)
from app.schemas.data_discovery import DataDiscoverySearchRequest
from app.services.catalog_query import (
    get_table,
    list_columns,
    list_indexes,
    list_relations,
)
from app.services.data_discovery_search import search_schema


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
        try:
            resolved, table_detail = get_table(db, source, schema, table)
            _, columns_page = list_columns(
                db,
                source,
                schema_name=schema,
                table_name=table,
                limit=500,
                offset=0,
            )
            _, relations_page = list_relations(
                db,
                source,
                schema_name=schema,
                table_name=table,
                limit=500,
                offset=0,
            )
            _, indexes_page = list_indexes(
                db,
                source,
                schema_name=schema,
                table_name=table,
                limit=500,
                offset=0,
            )
            columns = [item.model_dump(mode="json") for item in columns_page.items]
            primary_key_columns = [
                item.model_dump(mode="json")
                for item in columns_page.items
                if item.is_primary_key
            ]
            return {
                "source_name": resolved.source_name,
                "revision_id": resolved.revision_id,
                "schema_fingerprint": resolved.schema_fingerprint,
                "table": table_detail.model_dump(mode="json"),
                "columns": columns,
                "primary_key_columns": primary_key_columns,
                "relations": [
                    item.model_dump(mode="json") for item in relations_page.items
                ],
                "indexes": [
                    item.model_dump(mode="json") for item in indexes_page.items
                ],
            }
        except CatalogQueryError as exc:
            raise_from_discovery_or_catalog_error(exc)
        finally:
            if owns_session:
                db.close()


def get_mcp_application_adapter() -> McpApplicationAdapter:
    return McpApplicationAdapter()
