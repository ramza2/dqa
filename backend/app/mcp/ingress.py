"""Fail-closed MCP private-ingress checks (Phase 28-A hardening).

``DQA_MCP_BIND_HOST`` does **not** configure Uvicorn/ASGI listen addresses when
MCP is mounted into the shared backend process. It is a required private-boundary
declaration: only loopback values are accepted, and request peers must also be
loopback (or the test client in ``APP_ENV=test``). If the declaration is not
loopback, MCP is not mounted.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import Settings

_LOOPBACK_HOST_NAMES = frozenset({"127.0.0.1", "localhost", "::1"})


def is_loopback_host_declaration(host: str | None) -> bool:
    """Return True when ``host`` is an explicit loopback declaration."""
    value = (host or "").strip().lower()
    if not value:
        return False
    if value in _LOOPBACK_HOST_NAMES:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def should_mount_mcp(settings: Settings) -> bool:
    """Mount MCP only when enabled and private-boundary declaration is loopback."""
    if not settings.dqa_mcp_enabled:
        return False
    return is_loopback_host_declaration(settings.dqa_mcp_bind_host)


def peer_host_from_scope(scope: Scope) -> str | None:
    client = scope.get("client")
    if not client or not isinstance(client, (list, tuple)) or not client:
        return None
    host = client[0]
    return host if isinstance(host, str) else None


def is_trusted_mcp_peer(scope: Scope, settings: Settings) -> bool:
    """Allow only loopback peers; TestClient host is permitted in test env."""
    host = peer_host_from_scope(scope)
    if host is None:
        # No peer metadata: fail closed except deterministic test harness.
        return settings.app_env == "test"
    if host in _LOOPBACK_HOST_NAMES or host == "testclient":
        if host == "testclient":
            return settings.app_env in {"test", "development"}
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def ingress_rejected_response() -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={
            "detail": {
                "code": "MCP_INGRESS_DENIED",
                "message": "mcp ingress is restricted to trusted private peers",
            }
        },
    )


class McpIngressMiddleware:
    """Reject MCP requests from non-loopback peers (defense in depth)."""

    def __init__(self, app: ASGIApp, *, settings: Settings) -> None:
        self.app = app
        self._settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if not is_trusted_mcp_peer(scope, self._settings):
            response = ingress_rejected_response()
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


def wrap_mcp_ingress(app: ASGIApp, settings: Settings) -> ASGIApp:
    return McpIngressMiddleware(app, settings=settings)
