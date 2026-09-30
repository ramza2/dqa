"""FastAPI dependencies for authentication and permission checks."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status

from app.auth.errors import AuthError, AuthErrorCode
from app.auth.factory import create_identity_provider
from app.auth.models import AuthenticatedActor, Permission
from app.auth.actor import normalize_authenticated_actor
from app.auth.rbac import actor_has_permission
from app.core.config import Settings, get_settings


def get_current_actor(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthenticatedActor:
    """Authenticate the request via the configured IdentityProvider."""
    try:
        provider = create_identity_provider(settings)
        return normalize_authenticated_actor(provider.authenticate(request))
    except AuthError as exc:
        raise _auth_http_error(exc) from None


def require_permission(
    permission: Permission,
) -> Callable[..., AuthenticatedActor]:
    """Return a dependency that requires ``permission`` and yields the actor."""

    def _dependency(
        actor: AuthenticatedActor = Depends(get_current_actor),
    ) -> AuthenticatedActor:
        if not actor_has_permission(actor, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": AuthErrorCode.AUTHORIZATION_DENIED,
                    "message": "permission denied",
                },
            )
        return actor

    return _dependency


def _auth_http_error(exc: AuthError) -> HTTPException:
    if exc.code in {
        AuthErrorCode.PROVIDER_NOT_CONFIGURED,
        AuthErrorCode.PROVIDER_UNAVAILABLE,
    }:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code in {
        AuthErrorCode.AUTHENTICATION_REQUIRED,
        AuthErrorCode.AUTHENTICATION_INVALID,
    }:
        status_code = status.HTTP_401_UNAUTHORIZED
    elif exc.code == AuthErrorCode.AUTHORIZATION_DENIED:
        status_code = status.HTTP_403_FORBIDDEN
    else:
        status_code = status.HTTP_401_UNAUTHORIZED
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )
