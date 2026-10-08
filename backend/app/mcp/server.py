"""Build and mount the DQA MCP Streamable HTTP server (Phase 28-A/B)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.types import ASGIApp

from app.core.config import Settings
from app.mcp.auth import McpAuthMiddleware
from app.mcp.ingress import should_mount_mcp, wrap_mcp_ingress
from app.mcp.registry import McpToolRegistry, build_foundation_registry
from app.mcp.tools import describe_resource, mcp_ready, search_schema


def normalize_mcp_mount_path(path: str) -> str:
    raw = (path or "/mcp").strip() or "/mcp"
    if not raw.startswith("/"):
        raw = f"/{raw}"
    return raw.rstrip("/") or "/mcp"


def _transport_security(settings: Settings) -> TransportSecuritySettings:
    # Production keeps DNS-rebinding protection; development/test allow TestClient.
    if settings.app_env == "production":
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "127.0.0.1",
                "localhost",
                "127.0.0.1:*",
                "localhost:*",
            ],
            allowed_origins=[
                "http://127.0.0.1",
                "http://localhost",
                "http://127.0.0.1:*",
                "http://localhost:*",
            ],
        )
    return TransportSecuritySettings(enable_dns_rebinding_protection=False)


def _tool_description(registry: McpToolRegistry, name: str, fallback: str) -> str:
    entry = registry.get(name)
    return entry.description if entry is not None else fallback


def build_mcp_server(
    settings: Settings,
    *,
    registry: McpToolRegistry | None = None,
) -> tuple[FastMCP, McpToolRegistry]:
    """Construct FastMCP with foundation + Discovery tools (no Query tools)."""
    tool_registry = registry or build_foundation_registry()

    mcp = FastMCP(
        name="dqa-mcp",
        instructions=(
            "DEMIS Query Assistant MCP (Phase 28-B). "
            "Discovery tools: demis.search_schema, demis.describe_resource. "
            "Query preparation/execution tools are not available yet. "
            "Authenticate via the DQA IdentityProvider; never pass user_id/role "
            "in tool arguments. CATALOG_READ is required for Discovery tools."
        ),
        # Advisory only for standalone FastMCP.run(); mounted ASGI uses Uvicorn.
        host=settings.dqa_mcp_bind_host or "127.0.0.1",
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        max_request_body_size=int(settings.dqa_mcp_max_body_bytes),
        transport_security=_transport_security(settings),
    )

    @mcp.tool(
        name="dqa.mcp_ready",
        description=_tool_description(
            tool_registry, "dqa.mcp_ready", "MCP foundation readiness probe."
        ),
    )
    def _mcp_ready() -> dict[str, Any]:
        return mcp_ready()

    @mcp.tool(
        name="demis.search_schema",
        description=_tool_description(
            tool_registry,
            "demis.search_schema",
            "Search active Catalog schema metadata.",
        ),
    )
    def _search_schema(
        source_name: str,
        query: str,
        mode: str = "keyword",
        object_type: str | None = None,
        top_k: int = 10,
        expand_terms: bool = False,
        expand_relations: bool = False,
        max_relation_hops: int = 0,
    ) -> dict[str, Any]:
        return search_schema(
            source_name=source_name,
            query=query,
            mode=mode,
            object_type=object_type,
            top_k=top_k,
            expand_terms=expand_terms,
            expand_relations=expand_relations,
            max_relation_hops=max_relation_hops,
        )

    @mcp.tool(
        name="demis.describe_resource",
        description=_tool_description(
            tool_registry,
            "demis.describe_resource",
            "Describe one Catalog table resource.",
        ),
    )
    def _describe_resource(
        source_name: str,
        schema_name: str,
        table_name: str,
    ) -> dict[str, Any]:
        return describe_resource(
            source_name=source_name,
            schema_name=schema_name,
            table_name=table_name,
        )

    return mcp, tool_registry


def build_protected_mcp_asgi(
    settings: Settings,
    *,
    registry: McpToolRegistry | None = None,
) -> tuple[FastMCP, McpToolRegistry, ASGIApp, str] | None:
    """Build auth+ingress-wrapped MCP ASGI app, or None when mount is refused."""
    if not should_mount_mcp(settings):
        return None

    mcp, tool_registry = build_mcp_server(settings, registry=registry)
    mount_path = normalize_mcp_mount_path(settings.dqa_mcp_mount_path)
    streamable = mcp.streamable_http_app()
    authed: ASGIApp = McpAuthMiddleware(
        streamable,
        settings=settings,
        registry=tool_registry,
        max_body_bytes=int(settings.dqa_mcp_max_body_bytes),
    )
    protected = wrap_mcp_ingress(authed, settings)
    return mcp, tool_registry, protected, mount_path


def mount_mcp_asgi(
    application: FastAPI,
    *,
    mcp: FastMCP,
    registry: McpToolRegistry,
    asgi_app: ASGIApp,
    mount_path: str,
) -> None:
    application.mount(mount_path, asgi_app)
    application.state.dqa_mcp = mcp
    application.state.dqa_mcp_registry = registry
    application.state.dqa_mcp_mount_path = mount_path


@asynccontextmanager
async def mcp_session_lifespan(mcp: FastMCP | None) -> AsyncIterator[None]:
    """Run the MCP Streamable HTTP session manager when MCP is enabled."""
    if mcp is None:
        yield
        return
    async with mcp.session_manager.run():
        yield
