"""MCP tool registry (Phase 28-A foundation + 28-B Discovery tools)."""

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
    """Registry for Phase 28-A/B — foundation + Discovery tools (no Query tools)."""
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
    registry.register(
        McpToolRegistration(
            name="demis.search_schema",
            description=(
                "Search the active Catalog Package schema metadata for one source "
                "(keyword, semantic, or hybrid). Requires CATALOG_READ. Returns "
                "source, active revision, schema fingerprint, and ranked evidence. "
                "Does not execute DEMIS queries or mutate Catalog/index state."
            ),
            permission=Permission.CATALOG_READ,
            handler_name="search_schema",
        )
    )
    registry.register(
        McpToolRegistration(
            name="demis.describe_resource",
            description=(
                "Describe one Catalog table: columns, primary keys, foreign-key "
                "relations, and indexes for the active revision. Requires "
                "source_name, schema_name, and table_name plus CATALOG_READ. "
                "Does not invent logical clinical mappings or executable field "
                "capabilities (Phase 29)."
            ),
            permission=Permission.CATALOG_READ,
            handler_name="describe_resource",
        )
    )
    return registry
