"""MCP authentication middleware integrated with DQA IdentityProvider / RBAC.

Fail-closed: production with ``DQA_AUTH_PROVIDER=disabled`` rejects all MCP
access. ``dev_headers`` is never a production fallback (factory-enforced).

Caller-supplied ``user_id`` / ``role`` / ``permissions`` (headers or tool args)
are never trusted as identity.
"""

from __future__ import annotations

import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.auth.actor import normalize_authenticated_actor
from app.auth.errors import AuthError, AuthErrorCode
from app.auth.factory import create_identity_provider
from app.auth.models import AuthenticatedActor
from app.auth.rbac import actor_has_permission
from app.core.config import Settings, get_settings
from app.mcp.context import clear_mcp_actor, set_mcp_actor
from app.mcp.registry import McpToolRegistry

# Non-authoritative identity headers that must never grant access.
_FORGED_IDENTITY_HEADERS = frozenset(
    {
        "x-user-id",
        "x-userid",
        "x-user-role",
        "x-user-roles",
        "x-roles",
        "x-role",
        "x-permissions",
        "x-permission",
        "x-actor-id",
        "x-actor",
        "x-forwarded-user",
        "x-remote-user",
        "x-authenticated-user",
    }
)

_IDENTITY_ARG_KEYS = frozenset(
    {
        "user_id",
        "userid",
        "role",
        "roles",
        "permission",
        "permissions",
        "actor_id",
        "actor",
        "identity",
    }
)


def _auth_http_status(code: str) -> int:
    if code in {
        AuthErrorCode.PROVIDER_NOT_CONFIGURED,
        AuthErrorCode.PROVIDER_UNAVAILABLE,
    }:
        return 503
    if code == AuthErrorCode.AUTHORIZATION_DENIED:
        return 403
    return 401


def auth_error_response(exc: AuthError) -> JSONResponse:
    return JSONResponse(
        status_code=_auth_http_status(exc.code),
        content={"detail": {"code": exc.code, "message": exc.issue.message}},
    )


def reject_forged_identity_headers(request: Request) -> None:
    for name in request.headers.keys():
        if name.lower() in _FORGED_IDENTITY_HEADERS:
            raise AuthError(
                AuthErrorCode.AUTHENTICATION_INVALID,
                "forged identity assertion is rejected",
            )


def _contains_identity_keys(payload: Any) -> bool:
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(key, str) and key.casefold() in _IDENTITY_ARG_KEYS:
                return True
            if _contains_identity_keys(value):
                return True
    elif isinstance(payload, list):
        return any(_contains_identity_keys(item) for item in payload)
    return False


def reject_forged_identity_in_mcp_body(body: bytes) -> None:
    """Reject MCP JSON-RPC payloads that smuggle identity claims in arguments."""
    if not body:
        return
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    method = payload.get("method")
    params = payload.get("params")
    if not isinstance(params, dict):
        return
    top_level = {k: v for k, v in params.items() if k != "arguments"}
    if _contains_identity_keys(top_level):
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "forged identity assertion is rejected",
        )
    if method == "tools/call" and _contains_identity_keys(params.get("arguments")):
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "forged identity assertion is rejected",
        )


def enforce_tool_permission(
    body: bytes,
    actor: AuthenticatedActor,
    registry: McpToolRegistry,
) -> None:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict) or payload.get("method") != "tools/call":
        return
    params = payload.get("params")
    if not isinstance(params, dict):
        return
    name = params.get("name")
    if not isinstance(name, str):
        return
    tool = registry.get(name)
    if tool is None or tool.permission is None:
        return
    if not actor_has_permission(actor, tool.permission):
        raise AuthError(
            AuthErrorCode.AUTHORIZATION_DENIED,
            "permission denied",
        )


async def _read_body(receive: Receive) -> bytes:
    body = b""
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        body += message.get("body", b"")
        if not message.get("more_body"):
            break
    return body


class McpAuthMiddleware:
    """Pure ASGI auth wrapper (preserves ContextVar into tool handlers)."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings | None = None,
        registry: McpToolRegistry | None = None,
    ) -> None:
        self.app = app
        self._settings = settings
        self._registry = registry

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = self._settings or get_settings()
        clear_mcp_actor()
        body = await _read_body(receive)

        async def replay_receive() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(scope, replay_receive)
        try:
            reject_forged_identity_headers(request)
            reject_forged_identity_in_mcp_body(body)
            provider = create_identity_provider(settings)
            actor = normalize_authenticated_actor(
                provider.authenticate(request)  # type: ignore[arg-type]
            )
            if self._registry is not None and body:
                enforce_tool_permission(body, actor, self._registry)
            set_mcp_actor(actor)
            await self.app(scope, replay_receive, send)
        except AuthError as exc:
            response = auth_error_response(exc)
            await response(scope, receive, send)
        finally:
            clear_mcp_actor()
