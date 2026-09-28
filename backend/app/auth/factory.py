"""Create the configured IdentityProvider (fail-closed for unsafe configs)."""

from __future__ import annotations

from app.auth.dev_headers import DevHeadersIdentityProvider
from app.auth.errors import AuthError, AuthErrorCode
from app.auth.provider import IdentityProvider
from app.core.config import Settings

_DEV_HEADERS_ALLOWED_ENVS = frozenset({"development", "test"})


def create_identity_provider(settings: Settings) -> IdentityProvider:
    """Return the configured identity provider or raise a typed AuthError."""
    provider = settings.dqa_auth_provider
    if provider == "disabled":
        raise AuthError(
            AuthErrorCode.PROVIDER_NOT_CONFIGURED,
            "authentication provider is not configured",
        )
    if provider == "dev_headers":
        if settings.app_env not in _DEV_HEADERS_ALLOWED_ENVS:
            raise AuthError(
                AuthErrorCode.PROVIDER_UNAVAILABLE,
                "dev_headers identity provider is not available in this environment",
            )
        return DevHeadersIdentityProvider()
    raise AuthError(
        AuthErrorCode.PROVIDER_UNAVAILABLE,
        "authentication provider is unavailable",
    )
