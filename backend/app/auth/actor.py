"""Provider-independent AuthenticatedActor normalization."""

from __future__ import annotations

from collections.abc import Iterable

from app.auth.errors import AuthError, AuthErrorCode
from app.auth.models import AuthenticatedActor, Role

MAX_ACTOR_ID_LENGTH = 255


def normalize_authenticated_actor(actor: object) -> AuthenticatedActor:
    """Validate and normalize an actor returned by any IdentityProvider.

    Ensures blank/oversize/control-character actor ids and undeclared roles
    cannot reach application services or persistence. Failures map to
    ``AUTHENTICATION_INVALID``.
    """
    try:
        return _normalize(actor)
    except AuthError:
        raise
    except Exception:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "authenticated actor is invalid",
        ) from None


def _normalize(actor: object) -> AuthenticatedActor:
    if not isinstance(actor, AuthenticatedActor):
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "authenticated actor is invalid",
        )

    actor_id = _normalize_actor_id(actor.actor_id)
    provider = _normalize_provider(actor.provider)
    roles = _normalize_roles(actor.roles)
    display_name = actor.display_name
    if display_name is not None and not isinstance(display_name, str):
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "authenticated actor is invalid",
        )

    return AuthenticatedActor(
        actor_id=actor_id,
        roles=roles,
        provider=provider,
        display_name=display_name,
    )


def _normalize_actor_id(value: object) -> str:
    if not isinstance(value, str):
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "actor identity is invalid",
        )
    if _contains_control_chars(value):
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "actor identity is invalid",
        )
    actor_id = value.strip()
    if not actor_id or len(actor_id) > MAX_ACTOR_ID_LENGTH:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "actor identity is invalid",
        )
    return actor_id


def _normalize_provider(value: object) -> str:
    if not isinstance(value, str):
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "authenticated actor is invalid",
        )
    provider = value.strip()
    if not provider:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "authenticated actor is invalid",
        )
    return provider


def _normalize_roles(value: object) -> frozenset[Role]:
    if value is None:
        return frozenset()
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "authenticated actor is invalid",
        )
    roles: set[Role] = set()
    for item in value:
        if isinstance(item, Role):
            roles.add(item)
            continue
        if isinstance(item, str):
            try:
                roles.add(Role(item))
            except ValueError as exc:
                raise AuthError(
                    AuthErrorCode.AUTHENTICATION_INVALID,
                    "authenticated actor is invalid",
                ) from exc
            continue
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "authenticated actor is invalid",
        )
    return frozenset(roles)


def _contains_control_chars(value: str) -> bool:
    """Reject C0 controls and DEL (U+0000–U+001F, U+007F)."""
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)
