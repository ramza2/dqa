"""Typed authentication / authorization errors (sanitized messages only)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthIssue:
    code: str
    message: str


class AuthError(Exception):
    """Raised for authn/authz failures that map to HTTP responses."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = AuthIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class AuthErrorCode:
    PROVIDER_NOT_CONFIGURED = "AUTH_PROVIDER_NOT_CONFIGURED"
    PROVIDER_UNAVAILABLE = "AUTH_PROVIDER_UNAVAILABLE"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    AUTHENTICATION_INVALID = "AUTHENTICATION_INVALID"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
