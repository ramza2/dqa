"""Credential resolver boundary for live DEMIS adapter construction.

Actual secret-store implementations are out of scope. Callers supply a
resolver that maps ``credential_secret_ref`` to opaque runtime material.
Credential values must never be logged, persisted, put in errors, or returned
through public APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CredentialMaterial:
    """Opaque runtime credential payload.

    Representations deliberately omit secret contents so accidental logging of
    the object cannot leak passwords or tokens.
    """

    secret_ref: str
    # Opaque bytes/token holder — not for logging or API responses.
    _secret: str

    def get_secret(self) -> str:
        """Return the secret for driver use only. Never log the return value."""
        return self._secret

    def __repr__(self) -> str:
        return f"CredentialMaterial(secret_ref=<redacted>, configured=True)"

    def __str__(self) -> str:
        return "CredentialMaterial(<redacted>)"


class CredentialResolver(Protocol):
    """Resolve a Connection Profile credential reference to runtime material."""

    def resolve(self, credential_secret_ref: str) -> CredentialMaterial:
        """Resolve ``credential_secret_ref`` without logging secret values.

        Must raise ``DemisAdapterError`` with ``CREDENTIAL_UNAVAILABLE`` when
        the reference cannot be resolved. Must not echo the secret or DSN.
        """
        ...
