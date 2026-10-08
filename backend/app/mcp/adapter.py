"""Application-service adapter boundary for MCP tools.

MCP transport handlers and tools call this facade only. It must not open DEMIS
connections, execute SQL, or import Catalog packages. Future Discovery/Query
tools (28-B/C) will delegate into existing DQA application services from here.
"""

from __future__ import annotations

from typing import Any

from app.auth.models import AuthenticatedActor


class McpApplicationAdapter:
    """Thin, side-effect-free facade used by foundation MCP tools."""

    def readiness(self, actor: AuthenticatedActor) -> dict[str, Any]:
        """Return MCP foundation readiness (no DB / DEMIS / LLM I/O)."""
        return {
            "status": "ready",
            "phase": "28-A",
            "client": "MCP",
            "actor_id": actor.actor_id,
            "provider": actor.provider,
        }


def get_mcp_application_adapter() -> McpApplicationAdapter:
    return McpApplicationAdapter()
