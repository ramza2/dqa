"""Recommendation adapter package (typed errors only; no LLM transport here)."""

from app.adapters.recommendation.errors import (
    RecommendationError,
    RecommendationErrorCode,
    RecommendationIssue,
)

__all__ = [
    "RecommendationError",
    "RecommendationErrorCode",
    "RecommendationIssue",
]
