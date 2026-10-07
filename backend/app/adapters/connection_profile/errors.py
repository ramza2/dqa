"""Typed errors for Connection Profile management."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectionProfileIssue:
    code: str
    message: str


class ConnectionProfileError(Exception):
    """Raised when Connection Profile operations fail deterministically."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = ConnectionProfileIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class ConnectionProfileErrorCode:
    NOT_FOUND = "CONNECTION_PROFILE_NOT_FOUND"
    DUPLICATE_SOURCE_ENVIRONMENT = "CONNECTION_PROFILE_DUPLICATE_SOURCE_ENVIRONMENT"
    INVALID_REQUEST = "CONNECTION_PROFILE_INVALID_REQUEST"
    INTERNAL_ERROR = "CONNECTION_PROFILE_INTERNAL_ERROR"
