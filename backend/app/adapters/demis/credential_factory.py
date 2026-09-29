"""Factory for production CredentialResolver instances."""

from __future__ import annotations

from app.adapters.demis.credentials import CredentialResolver
from app.adapters.demis.env_credentials import (
    DEFAULT_DEMIS_CREDENTIAL_ENV_PREFIX,
    EnvironmentCredentialResolver,
)
from app.core.config import Settings, get_settings


def create_credential_resolver(
    settings: Settings | None = None,
) -> CredentialResolver:
    """Build the production CredentialResolver from settings.

    Currently returns ``EnvironmentCredentialResolver`` for the ``env:`` scheme
    boundary. Future approved secret stores may implement the same protocol.
    """
    cfg = settings or get_settings()
    prefix = (
        cfg.dqa_demis_credential_env_prefix or DEFAULT_DEMIS_CREDENTIAL_ENV_PREFIX
    )
    return EnvironmentCredentialResolver(env_prefix=prefix)
