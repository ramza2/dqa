"""Minimal MCP tool registry (Phase 28-A foundation only)."""

from __future__ import annotations

from dataclasses import dataclass

from app.auth.models import Permission


@dataclass(frozen=True)
class McpToolRegistration:
    """One registered MCP tool metadata entry."""

    name: str
    description: str
    # None => any authenticated actor; otherwise require this permission.
    permission: Permission | None
    # Handler is bound onto FastMCP; kept for introspection/tests.
    handler_name: str


class McpToolRegistry:
    """In-process registry of tools exposed over MCP."""

    def __init__(self) -> None:
        self._tools: dict[str, McpToolRegistration] = {}

    def register(self, tool: McpToolRegistration) -> None:
        if tool.name in self._tools:
            raise ValueError(f"duplicate MCP tool registration: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> McpToolRegistration | None:
        return self._tools.get(name)

    def list_tools(self) -> list[McpToolRegistration]:
        return sorted(self._tools.values(), key=lambda t: t.name)

    def names(self) -> list[str]:
        return [t.name for t in self.list_tools()]


def build_foundation_registry() -> McpToolRegistry:
    """Registry for Phase 28-A — no Discovery/Query tools."""
    registry = McpToolRegistry()
    registry.register(
        McpToolRegistration(
            name="dqa.mcp_ready",
            description=(
                "MCP foundation readiness probe. Returns sanitized status only; "
                "does not access DEMIS, Catalog data, or query execution."
            ),
            permission=None,
            handler_name="mcp_ready",
        )
    )
    return registry
