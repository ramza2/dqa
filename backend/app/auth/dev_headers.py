"""Development/test-only identity provider using trusted local headers.

Headers are NOT production credentials. Never enable this provider outside
development/test environments.
"""

from __future__ import annotations

from fastapi import Request

from app.auth.errors import AuthError, AuthErrorCode
from app.auth.models import AuthenticatedActor, Role
from app.auth.actor import MAX_ACTOR_ID_LENGTH

DEV_ACTOR_HEADER = "X-DQA-Dev-Actor"
DEV_ROLES_HEADER = "X-DQA-Dev-Roles"
PROVIDER_NAME = "dev_headers"

_ROLE_BY_VALUE = {role.value: role for role in Role}


class DevHeadersIdentityProvider:
    """Parse ``X-DQA-Dev-Actor`` / ``X-DQA-Dev-Roles`` into an actor.

    Environment gating is enforced by the factory before this provider is used.
    """

    def authenticate(self, request: Request) -> AuthenticatedActor:
        raw_actor = request.headers.get(DEV_ACTOR_HEADER)
        if raw_actor is None:
            raise AuthError(
                AuthErrorCode.AUTHENTICATION_REQUIRED,
                "authentication is required",
            )
        actor_id = _parse_actor_id(raw_actor)
        roles = _parse_roles(request.headers.get(DEV_ROLES_HEADER))
        return AuthenticatedActor(
            actor_id=actor_id,
            roles=roles,
            provider=PROVIDER_NAME,
        )


def _parse_actor_id(raw: str) -> str:
    if "\r" in raw or "\n" in raw:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "actor identity is invalid",
        )
    actor_id = raw.strip()
    if not actor_id:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "actor identity is invalid",
        )
    if len(actor_id) > MAX_ACTOR_ID_LENGTH:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "actor identity is invalid",
        )
    return actor_id


def _parse_roles(raw: str | None) -> frozenset[Role]:
    if raw is None or not raw.strip():
        return frozenset()
    if "\r" in raw or "\n" in raw:
        raise AuthError(
            AuthErrorCode.AUTHENTICATION_INVALID,
            "actor roles assertion is invalid",
        )
    roles: set[Role] = set()
    for segment in raw.split(","):
        token = segment.strip()
        if not token:
            # Trailing/duplicate commas are ignored; unknown roles fail closed.
            continue
        role = _ROLE_BY_VALUE.get(token)
        if role is None:
            raise AuthError(
                AuthErrorCode.AUTHENTICATION_INVALID,
                "actor roles assertion is invalid",
            )
        roles.add(role)
    return frozenset(roles)
