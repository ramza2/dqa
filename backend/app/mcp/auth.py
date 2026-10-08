"""MCP authentication middleware integrated with DQA IdentityProvider / RBAC.

Fail-closed: production with ``DQA_AUTH_PROVIDER=disabled`` rejects all MCP
access. ``dev_headers`` is never a production fallback (factory-enforced).

Caller-supplied ``user_id`` / ``role`` / ``permissions`` (headers or tool args)
are never trusted as identity.

Request bodies are read with a hard byte bound (413 when exceeded). Disconnects
and malformed request streams fail closed without unbounded buffering.
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

# Default matches a conservative MCP JSON-RPC envelope size (overridable).
DEFAULT_MCP_MAX_BODY_BYTES = 1_048_576

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


class McpBodyTooLargeError(Exception):
    """Request body exceeds the configured MCP maximum."""


class McpBodyStreamError(Exception):
    """Client disconnect or malformed/incomplete HTTP request stream."""


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


def body_too_large_response() -> JSONResponse:
    return JSONResponse(
        status_code=413,
        content={
            "detail": {
                "code": "MCP_BODY_TOO_LARGE",
                "message": "mcp request body exceeds the allowed size",
            }
        },
    )


def body_stream_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "detail": {
                "code": "MCP_BODY_INCOMPLETE",
                "message": "mcp request body is incomplete or malformed",
            }
        },
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


def content_length_exceeds(scope: Scope, max_bytes: int) -> bool:
    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in scope.get("headers", [])
    }
    raw = headers.get("content-length")
    if raw is None:
        return False
    try:
        length = int(raw)
    except ValueError:
        return False
    return length > max_bytes


async def read_body_bounded(receive: Receive, *, max_bytes: int) -> bytes:
    """Read an HTTP request body with a hard size bound.

    Raises:
        McpBodyTooLargeError: accumulated bytes would exceed ``max_bytes``
        McpBodyStreamError: disconnect or non-request stream message
    """
    if max_bytes < 0:
        raise McpBodyTooLargeError()
    body = bytearray()
    # Bound receive iterations so empty more_body frames cannot spin forever.
    max_frames = max_bytes + 8
    frames = 0
    while True:
        frames += 1
        if frames > max_frames:
            raise McpBodyStreamError("malformed request stream")
        message = await receive()
        msg_type = message.get("type")
        if msg_type == "http.disconnect":
            raise McpBodyStreamError("client disconnected")
        if msg_type != "http.request":
            # Unknown/unexpected stream frames must not spin forever.
            raise McpBodyStreamError("malformed request stream")
        chunk = message.get("body", b"") or b""
        if len(body) + len(chunk) > max_bytes:
            raise McpBodyTooLargeError()
        body.extend(chunk)
        if not message.get("more_body"):
            return bytes(body)


class McpAuthMiddleware:
    """Pure ASGI auth wrapper (preserves ContextVar into tool handlers)."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings | None = None,
        registry: McpToolRegistry | None = None,
        max_body_bytes: int | None = None,
    ) -> None:
        self.app = app
        self._settings = settings
        self._registry = registry
        self._max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = self._settings or get_settings()
        max_bytes = (
            self._max_body_bytes
            if self._max_body_bytes is not None
            else int(settings.dqa_mcp_max_body_bytes)
        )
        clear_mcp_actor()

        if content_length_exceeds(scope, max_bytes):
            response = body_too_large_response()
            await response(scope, receive, send)
            return

        try:
            body = await read_body_bounded(receive, max_bytes=max_bytes)
        except McpBodyTooLargeError:
            response = body_too_large_response()
            await response(scope, receive, send)
            return
        except McpBodyStreamError:
            response = body_stream_error_response()
            await response(scope, receive, send)
            return

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
