"""Application-service adapter boundary for MCP tools.

MCP transport handlers and tools call this facade only. Discovery tools (28-B)
and Template Query tools (28-C) delegate into existing DQA application services.
No parallel execution/audit path. Identity is never taken from tool arguments.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryError
from app.adapters.data_discovery.errors import DataDiscoveryError
from app.adapters.db.session import get_session_factory
from app.adapters.demis.errors import DemisAdapterError
from app.adapters.embedding.factory import create_embedding_provider
from app.adapters.execution.errors import (
    ExecutionError,
    ExecutionErrorCode,
    ExecutionPreviewError,
)
from app.auth.errors import AuthError, AuthErrorCode
from app.auth.models import AuthenticatedActor, Permission
from app.auth.rbac import actor_has_permission
from app.core.config import Settings, get_settings
from app.domain.data_discovery import DataDiscoverySearchMode
from app.mcp.errors import (
    is_clarification_error,
    public_execution_error_payload,
    raise_catalog_revision_changed,
    raise_execution_binding_mismatch,
    raise_from_discovery_or_catalog_error,
    raise_from_execution_error,
    raise_invalid_tool_arguments,
    raise_query_execution_disabled,
)
from app.mcp.execution_token import (
    McpExecutionTokenError,
    issue_execution_token,
    verify_execution_token,
)
from app.schemas.data_discovery import DataDiscoverySearchRequest
from app.schemas.execution_preview import ExecutionPreviewRequest
from app.services.catalog_query import (
    PageResult,
    ResolvedActiveRevision,
    get_table,
    list_columns,
    list_indexes,
    list_relations,
)
from app.services.data_discovery_search import search_schema
from app.services.execution_eligibility import evaluate_execution_eligibility
from app.services.query_execution import execute_query

# Bound for describe_resource metadata collections (columns / relations / indexes).
_DESCRIBE_COLLECTION_LIMIT = 500

PrepareStatus = str  # READY | NEEDS_CLARIFICATION | BLOCKED


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


def _redacted_prepare_metadata(
    *,
    source_name: str,
    environment: str,
    catalog_revision_id: int | None,
    catalog_fingerprint: str | None,
    template_id: int | None,
    version_id: int | None,
    version: int | None,
    connection_profile_id: int | None,
    parameter_names: list[str],
    sensitive_parameter_names: list[str],
    row_limit: int | None,
    timeout_seconds: int | None,
) -> dict[str, Any]:
    """Public prepare fields — never include SQL, credentials, or parameter values."""
    return {
        "source_name": source_name,
        "environment": environment,
        "catalog_revision_id": catalog_revision_id,
        "catalog_fingerprint": catalog_fingerprint,
        "template_id": template_id,
        "version_id": version_id,
        "version": version,
        "connection_profile_id": connection_profile_id,
        "parameter_names": parameter_names,
        "sensitive_parameter_names": sensitive_parameter_names,
        "row_limit": row_limit,
        "timeout_seconds": timeout_seconds,
    }


class McpApplicationAdapter:
    """Facade used by MCP tools — reuses application services, never HTTP loopback."""

    def readiness(self, actor: AuthenticatedActor) -> dict[str, Any]:
        """Return MCP foundation readiness (no DB / DEMIS / LLM I/O)."""
        return {
            "status": "ready",
            "phase": "28-C",
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

    def require_query_operate(self, actor: AuthenticatedActor) -> None:
        """Enforce QUERY_OPERATE at the tool/service boundary (defense in depth)."""
        if not actor_has_permission(actor, Permission.QUERY_OPERATE):
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

    def prepare_query(
        self,
        actor: AuthenticatedActor,
        *,
        source_name: str,
        environment: str,
        template_id: int,
        version_id: int,
        parameters: dict[str, Any] | None = None,
        settings: Settings | None = None,
        session: Session | None = None,
    ) -> dict[str, Any]:
        """Prepare an Approved Template query (no DEMIS / credentials / audit / SQL run).

        Returns deterministic READY / NEEDS_CLARIFICATION / BLOCKED. Issues an
        opaque execution token only for READY.
        """
        self.require_query_operate(actor)
        try:
            request = ExecutionPreviewRequest(
                source_name=source_name,
                environment=environment,
                template_id=template_id,
                version_id=version_id,
                parameters=parameters or {},
            )
        except (ValidationError, ValueError, TypeError):
            raise_invalid_tool_arguments()

        cfg = settings or get_settings()
        owns_session = session is None
        db = session or get_session_factory()()
        try:
            try:
                eligibility = evaluate_execution_eligibility(
                    db,
                    source_name=request.source_name,
                    environment=request.environment,
                    template_id=request.template_id,
                    version_id=request.version_id,
                    parameters=request.parameters,
                )
            except ExecutionPreviewError as exc:
                error = public_execution_error_payload(exc.code)
                status: PrepareStatus = (
                    "NEEDS_CLARIFICATION"
                    if is_clarification_error(exc.code)
                    else "BLOCKED"
                )
                return {
                    "status": status,
                    **_redacted_prepare_metadata(
                        source_name=request.source_name,
                        environment=request.environment,
                        catalog_revision_id=None,
                        catalog_fingerprint=None,
                        template_id=request.template_id,
                        version_id=request.version_id,
                        version=None,
                        connection_profile_id=None,
                        parameter_names=sorted(request.parameters.keys()),
                        sensitive_parameter_names=[],
                        row_limit=None,
                        timeout_seconds=None,
                    ),
                    "execution_token": None,
                    "token_expires_at": None,
                    "blockers": [] if status == "NEEDS_CLARIFICATION" else [exc.code],
                    "error": error,
                }

            parameter_names = sorted(eligibility.resolved_parameters.keys())
            meta = _redacted_prepare_metadata(
                source_name=eligibility.source_name,
                environment=eligibility.environment,
                catalog_revision_id=eligibility.catalog_revision_id,
                catalog_fingerprint=eligibility.catalog_fingerprint,
                template_id=eligibility.template.id,
                version_id=eligibility.version.id,
                version=eligibility.version.version,
                connection_profile_id=eligibility.connection_profile.id,
                parameter_names=parameter_names,
                sensitive_parameter_names=list(eligibility.sensitive_parameter_names),
                row_limit=eligibility.row_limit,
                timeout_seconds=eligibility.timeout_seconds,
            )

            if not eligibility.execution_available:
                return {
                    "status": "BLOCKED",
                    **meta,
                    "execution_token": None,
                    "token_expires_at": None,
                    "blockers": list(eligibility.execution_blockers),
                    "error": public_execution_error_payload(
                        ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE
                    ),
                }

            try:
                token, expires_at = issue_execution_token(
                    actor=actor,
                    source_name=eligibility.source_name,
                    environment=eligibility.environment,
                    template_id=eligibility.template.id,
                    version_id=eligibility.version.id,
                    catalog_revision_id=eligibility.catalog_revision_id,
                    catalog_fingerprint=eligibility.catalog_fingerprint,
                    connection_profile_id=eligibility.connection_profile.id,
                    parameters=dict(eligibility.resolved_parameters),
                    sensitive_parameter_names=list(eligibility.sensitive_parameter_names),
                    settings=cfg,
                )
            except McpExecutionTokenError as exc:
                return {
                    "status": "BLOCKED",
                    **meta,
                    "execution_token": None,
                    "token_expires_at": None,
                    "blockers": [exc.code],
                    "error": public_execution_error_payload(exc.code),
                }

            return {
                "status": "READY",
                **meta,
                "execution_token": token,
                "token_expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                "blockers": [],
                "error": None,
            }
        finally:
            if owns_session:
                db.close()

    def execute_query(
        self,
        actor: AuthenticatedActor,
        *,
        execution_token: str,
        settings: Settings | None = None,
        session: Session | None = None,
        **execute_kwargs: Any,
    ) -> dict[str, Any]:
        """Execute via opaque token only — reuses ``app.services.query_execution``."""
        self.require_query_operate(actor)
        cfg = settings or get_settings()
        if not cfg.dqa_mcp_query_execution_enabled:
            raise_query_execution_disabled()

        token_value = (execution_token or "").strip()
        if not token_value:
            raise_invalid_tool_arguments()

        try:
            claims = verify_execution_token(token_value, actor=actor, settings=cfg)
        except McpExecutionTokenError as exc:
            raise_from_execution_error(exc)

        owns_session = session is None
        db = session or get_session_factory()()
        try:
            request = ExecutionPreviewRequest(
                source_name=claims.source_name,
                environment=claims.environment,
                template_id=claims.template_id,
                version_id=claims.version_id,
                parameters=dict(claims.parameters),
            )
            # Revalidate eligibility + token binding before the shared execute path.
            try:
                eligibility = evaluate_execution_eligibility(
                    db,
                    source_name=request.source_name,
                    environment=request.environment,
                    template_id=request.template_id,
                    version_id=request.version_id,
                    parameters=request.parameters,
                )
            except ExecutionPreviewError as exc:
                raise_from_execution_error(exc)

            if (
                eligibility.source_name != claims.source_name
                or eligibility.environment != claims.environment
                or eligibility.template.id != claims.template_id
                or eligibility.version.id != claims.version_id
                or eligibility.catalog_revision_id != claims.catalog_revision_id
                or eligibility.catalog_fingerprint != claims.catalog_fingerprint
                or eligibility.connection_profile.id != claims.connection_profile_id
            ):
                raise_execution_binding_mismatch()

            try:
                response = execute_query(
                    db,
                    request,
                    actor=actor,
                    **execute_kwargs,
                )
            except (ExecutionPreviewError, ExecutionError, DemisAdapterError) as exc:
                raise_from_execution_error(exc)

            payload = response.model_dump(mode="json")
            # Defense: never include SQL / credential fields (model has none).
            assert "sql_text" not in payload
            assert "host" not in payload
            assert "credential_secret_ref" not in payload
            return payload
        finally:
            if owns_session:
                db.close()


def get_mcp_application_adapter() -> McpApplicationAdapter:
    return McpApplicationAdapter()
