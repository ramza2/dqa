"""Sanitized Production Readiness Report schemas (no secrets / DEMIS live data)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CheckStatus = Literal["PASS", "BLOCKED", "ACTION_REQUIRED"]
OverallStatus = Literal["READY", "NOT_READY"]

CheckCode = Literal[
    "MIGRATIONS_AT_HEAD",
    "AUTH_PROVIDER",
    "ACTIVE_CATALOG",
    "QUERY_TEMPLATE",
    "CONNECTION_PROFILE",
    "DEMIS_ADAPTER",
    "LIVE_CONNECTIVITY",
    "EXTERNAL_READONLY_PRIVILEGE",
]


class ReadinessCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: CheckCode
    status: CheckStatus
    message: str = Field(min_length=1, max_length=512)


class ProductionReadinessReport(BaseModel):
    """Operator-facing readiness report for one source/environment binding."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    environment: str
    overall_status: OverallStatus
    checks: list[ReadinessCheckResult]
