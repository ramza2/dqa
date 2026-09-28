"""Identity provider protocol (future OIDC/JWT adapters implement this)."""

from __future__ import annotations

from typing import Protocol

from fastapi import Request

from app.auth.models import AuthenticatedActor


class IdentityProvider(Protocol):
    """Authenticate an HTTP request into an ``AuthenticatedActor``."""

    def authenticate(self, request: Request) -> AuthenticatedActor:
        """Return an authenticated actor or raise ``AuthError``."""
        ...
