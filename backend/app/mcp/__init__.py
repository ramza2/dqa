"""MCP server foundation (Phase 28-A).

Transport, auth integration, and tool-registry boundary only.
Discovery/Query tools are Phase 28-B/C. No DEMIS access in this package.
"""

from app.mcp.server import build_protected_mcp_asgi, mount_mcp_asgi

__all__ = ["build_protected_mcp_asgi", "mount_mcp_asgi"]
