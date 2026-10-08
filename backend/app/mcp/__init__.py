"""MCP server (Phase 28-A/B/C).

Transport, auth, Discovery tools, and Template Query prepare/execute tools.
Execute reuses the shared read-only DEMIS + durable audit path. No Dynamic Query.
"""

from app.mcp.server import build_protected_mcp_asgi, mount_mcp_asgi

__all__ = ["build_protected_mcp_asgi", "mount_mcp_asgi"]
