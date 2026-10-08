"""Foundation MCP tool handlers (no DEMIS / SQL / Catalog side effects)."""

from __future__ import annotations

from typing import Any

from app.auth.errors import AuthError, AuthErrorCode
from app.mcp.adapter import McpApplicationAdapter, get_mcp_application_adapter
from app.mcp.context import get_mcp_actor


def mcp_ready(
    *,
    adapter: McpApplicationAdapter | None = None,
) -> dict[str, Any]:
    """Authenticated readiness probe for MCP foundation tests and operators."""
    actor = get_mcp_actor()
    if actor is None:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_REQUIRED,
            "authentication is required",
        )
    facade = adapter or get_mcp_application_adapter()
    return facade.readiness(actor)
