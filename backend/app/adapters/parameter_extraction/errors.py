"""Typed errors for Parameter Extraction."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterExtractionIssue:
    code: str
    message: str


class ParameterExtractionError(Exception):
    """Raised for extraction protocol/system failures (sanitized messages only)."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = ParameterExtractionIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class ParameterExtractionErrorCode:
    TEMPLATE_NOT_FOUND = "PARAMETER_EXTRACTION_TEMPLATE_NOT_FOUND"
    TEMPLATE_NOT_ELIGIBLE = "PARAMETER_EXTRACTION_TEMPLATE_NOT_ELIGIBLE"
    STALE_VERSION = "PARAMETER_EXTRACTION_STALE_VERSION"
    ACTIVE_CATALOG_NOT_FOUND = "PARAMETER_EXTRACTION_ACTIVE_CATALOG_NOT_FOUND"
    EGRESS_NOT_ALLOWED = "PARAMETER_EXTRACTION_EGRESS_NOT_ALLOWED"
    PROMPT_TOO_LARGE = "PARAMETER_EXTRACTION_PROMPT_TOO_LARGE"
    LLM_NOT_CONFIGURED = "PARAMETER_EXTRACTION_LLM_NOT_CONFIGURED"
    LLM_UNAVAILABLE = "PARAMETER_EXTRACTION_LLM_UNAVAILABLE"
    LLM_OUTPUT_INVALID = "PARAMETER_EXTRACTION_LLM_OUTPUT_INVALID"
    PARAMETER_SCHEMA_INVALID = "PARAMETER_EXTRACTION_PARAMETER_SCHEMA_INVALID"
