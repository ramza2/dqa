"""MCP server (Phase 28-A foundation + 28-B Discovery tools).

Transport, auth integration, tool registry, and Discovery adapters.
Query tools are Phase 28-C. No DEMIS access or query execution in this package.
"""

from app.mcp.server import build_protected_mcp_asgi, mount_mcp_asgi

__all__ = ["build_protected_mcp_asgi", "mount_mcp_asgi"]
