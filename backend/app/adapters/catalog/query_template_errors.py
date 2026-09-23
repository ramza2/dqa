"""Structured errors for Query Template registry and approval workflow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class QueryTemplateIssue:
    code: str
    message: str


class QueryTemplateError(Exception):
    """Raised when Query Template registry operations fail deterministically."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = QueryTemplateIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class QueryTemplateErrorCode:
    TEMPLATE_NOT_FOUND = "QUERY_TEMPLATE_NOT_FOUND"
    VERSION_NOT_FOUND = "QUERY_TEMPLATE_VERSION_NOT_FOUND"
    ACTIVE_CATALOG_NOT_FOUND = "QUERY_TEMPLATE_ACTIVE_CATALOG_NOT_FOUND"
    DUPLICATE_STABLE_KEY = "QUERY_TEMPLATE_DUPLICATE_STABLE_KEY"
    INVALID_PARAMETER_SCHEMA = "QUERY_TEMPLATE_INVALID_PARAMETER_SCHEMA"
    INVALID_TARGET_SCHEMA = "QUERY_TEMPLATE_INVALID_TARGET_SCHEMA"
    NOT_DRAFT = "QUERY_TEMPLATE_NOT_DRAFT"
    INVALID_REQUEST = "QUERY_TEMPLATE_INVALID_REQUEST"
    INVALID_TRANSITION = "QUERY_TEMPLATE_INVALID_TRANSITION"
    STABLE_METADATA_FROZEN = "QUERY_TEMPLATE_STABLE_METADATA_FROZEN"
    INCOMPATIBLE_CATALOG = "QUERY_TEMPLATE_INCOMPATIBLE_CATALOG"
