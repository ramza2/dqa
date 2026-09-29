"""Environment-backed CredentialResolver (env: scheme only).

Resolves ``env:<ENV_VAR_NAME>`` references against process environment variables
that start with a configured dedicated prefix. Does not allow arbitrary env
access, secret-store schemes, or treating the reference string as a password.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping

from app.adapters.demis.credentials import CredentialMaterial
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode

_ENV_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ENV_SCHEME_PREFIX = "env:"
DEFAULT_DEMIS_CREDENTIAL_ENV_PREFIX = "DEMIS_SECRET_"


def validate_demis_credential_env_prefix(prefix: str) -> str:
    """Validate and normalize the dedicated DEMIS credential env prefix.

    Must match ``[A-Z][A-Z0-9_]*``. Never echo the invalid value in raised errors.
    """
    cleaned = (prefix or "").strip()
    if not cleaned or _ENV_NAME_PATTERN.fullmatch(cleaned) is None:
        raise DemisAdapterError(
            DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED,
            "demis credential environment prefix is invalid",
        )
    return cleaned


class EnvironmentCredentialResolver:
    """Production CredentialResolver for explicit ``env:`` references only."""

    def __init__(
        self,
        *,
        env_prefix: str = DEFAULT_DEMIS_CREDENTIAL_ENV_PREFIX,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._env_prefix = validate_demis_credential_env_prefix(env_prefix)
        # Copy mapping for tests; default reads live process env at resolve time
        # via os.environ when environ is None.
        self._environ = dict(environ) if environ is not None else None

    @property
    def env_prefix(self) -> str:
        return self._env_prefix

    def resolve(self, credential_secret_ref: str) -> CredentialMaterial:
        """Resolve an ``env:`` reference within the configured prefix boundary.

        Fail-closed for unsupported schemes, invalid names, wrong prefix,
        missing variables, and empty values. Sanitized errors never include the
        secret, reference, or environment variable name.
        """
        ref = (credential_secret_ref or "").strip()
        if not ref:
            raise DemisAdapterError(
                DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
                "credential reference could not be resolved",
            )

        if not ref.startswith(_ENV_SCHEME_PREFIX):
            # Unsupported scheme, plain password, blank scheme, etc.
            raise DemisAdapterError(
                DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
                "credential reference could not be resolved",
            )

        env_name = ref[len(_ENV_SCHEME_PREFIX) :]
        if not env_name or _ENV_NAME_PATTERN.fullmatch(env_name) is None:
            raise DemisAdapterError(
                DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
                "credential reference could not be resolved",
            )

        if not env_name.startswith(self._env_prefix):
            raise DemisAdapterError(
                DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
                "credential reference could not be resolved",
            )

        value = self._lookup(env_name)
        if value is None or value == "":
            raise DemisAdapterError(
                DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
                "credential reference could not be resolved",
            )

        return CredentialMaterial(secret_ref=ref, _secret=value)

    def _lookup(self, env_name: str) -> str | None:
        if self._environ is not None:
            return self._environ.get(env_name)
        return os.environ.get(env_name)
