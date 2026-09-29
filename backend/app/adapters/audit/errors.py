"""Typed errors for Query Audit foundation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuditIssue:
    code: str
    message: str


class AuditError(Exception):
    """Raised when audit write/read operations fail deterministically."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = AuditIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class AuditErrorCode:
    NOT_FOUND = "AUDIT_EVENT_NOT_FOUND"
    INVALID_REQUEST = "AUDIT_EVENT_INVALID_REQUEST"
    UNAVAILABLE = "AUDIT_UNAVAILABLE"
