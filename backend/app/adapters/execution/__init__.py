"""Execution eligibility / preview adapter package."""

from __future__ import annotations

from app.adapters.execution.errors import (
    ExecutionPreviewError,
    ExecutionPreviewErrorCode,
)

__all__ = [
    "ExecutionPreviewError",
    "ExecutionPreviewErrorCode",
]
