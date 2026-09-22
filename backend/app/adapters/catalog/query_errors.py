"""Structured errors for Active Catalog query APIs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogQueryIssue:
    code: str
    message: str


class CatalogQueryError(Exception):
    """Raised when an Active Catalog metadata query fails deterministically."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = CatalogQueryIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class CatalogQueryErrorCode:
    ACTIVE_REVISION_NOT_FOUND = "CATALOG_ACTIVE_REVISION_NOT_FOUND"
    TABLE_NOT_FOUND = "CATALOG_TABLE_NOT_FOUND"
