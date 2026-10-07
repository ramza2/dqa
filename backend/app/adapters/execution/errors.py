"""Typed errors for execution eligibility / preview / orchestration."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionPreviewIssue:
    code: str
    message: str


class ExecutionPreviewError(Exception):
    """Sanitized eligibility/preview failure. Never embed secrets, SQL, or values."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = ExecutionPreviewIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class ExecutionPreviewErrorCode:
    TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
    TEMPLATE_NOT_ELIGIBLE = "TEMPLATE_NOT_ELIGIBLE"
    STALE_TEMPLATE_VERSION = "STALE_TEMPLATE_VERSION"
    ACTIVE_CATALOG_NOT_FOUND = "ACTIVE_CATALOG_NOT_FOUND"
    CATALOG_MISMATCH = "CATALOG_MISMATCH"
    SQL_UNSAFE = "SQL_UNSAFE"
    PARAMETER_SCHEMA_INVALID = "PARAMETER_SCHEMA_INVALID"
    PARAMETER_UNDECLARED = "PARAMETER_UNDECLARED"
    PARAMETER_INVALID = "PARAMETER_INVALID"
    CONNECTION_PROFILE_NOT_FOUND = "CONNECTION_PROFILE_NOT_FOUND"
    CONNECTION_PROFILE_DISABLED = "CONNECTION_PROFILE_DISABLED"
    CONNECTION_PROFILE_INCOMPLETE = "CONNECTION_PROFILE_INCOMPLETE"
    INTERNAL_ERROR = "EXECUTION_PREVIEW_INTERNAL_ERROR"


@dataclass(frozen=True)
class ExecutionIssue:
    code: str
    message: str


class ExecutionError(Exception):
    """Sanitized execution failure. Never embed secrets, SQL, or result rows."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = ExecutionIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code

    @property
    def failure_category(self) -> str:
        return self.issue.code


class ExecutionErrorCode:
    AUDIT_UNAVAILABLE = "AUDIT_UNAVAILABLE"
    DEMIS_ADAPTER_UNAVAILABLE = "DEMIS_ADAPTER_UNAVAILABLE"
    INTERNAL_ERROR = "QUERY_EXECUTION_INTERNAL_ERROR"
