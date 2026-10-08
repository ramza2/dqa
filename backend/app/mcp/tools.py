"""MCP tool handlers (Phase 28-A foundation + 28-B Discovery).

No DEMIS adapter access, no query execution, no Catalog mutation.
Identity always comes from MCP request context — never from tool arguments.
"""

from __future__ import annotations

from typing import Any

from app.auth.errors import AuthError, AuthErrorCode
from app.mcp.adapter import McpApplicationAdapter, get_mcp_application_adapter
from app.mcp.context import get_mcp_actor


def _require_actor():
    actor = get_mcp_actor()
    if actor is None:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_REQUIRED,
            "authentication is required",
        )
    return actor


def mcp_ready(
    *,
    adapter: McpApplicationAdapter | None = None,
) -> dict[str, Any]:
    """Authenticated readiness probe for MCP foundation tests and operators."""
    actor = _require_actor()
    facade = adapter or get_mcp_application_adapter()
    return facade.readiness(actor)


def search_schema(
    *,
    source_name: str,
    query: str,
    mode: str = "keyword",
    object_type: str | None = None,
    top_k: int = 10,
    expand_terms: bool = False,
    expand_relations: bool = False,
    max_relation_hops: int = 0,
    adapter: McpApplicationAdapter | None = None,
) -> dict[str, Any]:
    """demis.search_schema — active Catalog discovery search."""
    actor = _require_actor()
    facade = adapter or get_mcp_application_adapter()
    return facade.search_schema(
        actor,
        source_name=source_name,
        query=query,
        mode=mode,
        object_type=object_type,
        top_k=top_k,
        expand_terms=expand_terms,
        expand_relations=expand_relations,
        max_relation_hops=max_relation_hops,
    )


def describe_resource(
    *,
    source_name: str,
    schema_name: str,
    table_name: str,
    adapter: McpApplicationAdapter | None = None,
) -> dict[str, Any]:
    """demis.describe_resource — Catalog table/column/PK/FK/index metadata."""
    actor = _require_actor()
    facade = adapter or get_mcp_application_adapter()
    return facade.describe_resource(
        actor,
        source_name=source_name,
        schema_name=schema_name,
        table_name=table_name,
    )
