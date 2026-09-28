"""Typed errors for Query Template recommendation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationIssue:
    code: str
    message: str


class RecommendationError(Exception):
    """Raised when recommendation fails deterministically (sanitized messages only)."""

    def __init__(self, code: str, message: str) -> None:
        self.issue = RecommendationIssue(code=code, message=message)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code


class RecommendationErrorCode:
    ACTIVE_CATALOG_NOT_FOUND = "RECOMMENDATION_ACTIVE_CATALOG_NOT_FOUND"
    LLM_NOT_CONFIGURED = "RECOMMENDATION_LLM_NOT_CONFIGURED"
    LLM_UNAVAILABLE = "RECOMMENDATION_LLM_UNAVAILABLE"
    LLM_OUTPUT_INVALID = "RECOMMENDATION_LLM_OUTPUT_INVALID"
    INVALID_REQUEST = "RECOMMENDATION_INVALID_REQUEST"
    PROMPT_TOO_LARGE = "RECOMMENDATION_PROMPT_TOO_LARGE"
