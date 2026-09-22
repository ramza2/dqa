"""Structured errors for Active Catalog management."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogActivationIssue:
    """Single structured activation issue (safe for API responses)."""

    code: str
    message: str


class CatalogActivationError(Exception):
    """Raised when activation or active-catalog lookup fails deterministically."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = CatalogActivationIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class CatalogActivationErrorCode:
    IMPORT_NOT_FOUND = "CATALOG_IMPORT_NOT_FOUND"
    REVISION_NOT_ACTIVATABLE = "CATALOG_REVISION_NOT_ACTIVATABLE"
    ACTIVE_REVISION_NOT_FOUND = "CATALOG_ACTIVE_REVISION_NOT_FOUND"
