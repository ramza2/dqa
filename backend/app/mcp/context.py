"""Request-scoped MCP actor context (never taken from tool arguments)."""

from __future__ import annotations

from contextvars import ContextVar

from app.auth.models import AuthenticatedActor

_mcp_actor: ContextVar[AuthenticatedActor | None] = ContextVar("dqa_mcp_actor", default=None)


def set_mcp_actor(actor: AuthenticatedActor) -> None:
    _mcp_actor.set(actor)


def get_mcp_actor() -> AuthenticatedActor | None:
    return _mcp_actor.get()


def clear_mcp_actor() -> None:
    _mcp_actor.set(None)
