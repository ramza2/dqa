"""DBMS-neutral request / result / diagnostics DTOs for DEMIS read-only access."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Bound execution contract limits (application may tighten further per template).
MAX_TIMEOUT_SECONDS = 300
MAX_ROW_LIMIT = 10_000
MAX_SQL_TEXT_LENGTH = 100_000


class ReadonlyQueryRequest(BaseModel):
    """Single read-only execution request supplied by the application layer.

    Contains only already-approved SQL text and bound parameter mappings.
    The adapter must not generate, modify, or interpolate SQL.
    """

    model_config = ConfigDict(extra="forbid")

    sql_text: str = Field(min_length=1, max_length=MAX_SQL_TEXT_LENGTH)
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(gt=0, le=MAX_TIMEOUT_SECONDS)
    row_limit: int = Field(gt=0, le=MAX_ROW_LIMIT)

    @field_validator("sql_text")
    @classmethod
    def sql_text_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("sql_text must not be blank")
        return cleaned


class ReadonlyQueryResult(BaseModel):
    """Normalized read-only query result.

    ``rows`` may contain sensitive medical data. Callers must never log, persist,
    put into exceptions, or send rows to an LLM.
    """

    model_config = ConfigDict(extra="forbid")

    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    truncated: bool
    elapsed_ms: int = Field(ge=0)

    def __repr__(self) -> str:
        # Intentionally omit row payloads from default representation.
        return (
            "ReadonlyQueryResult("
            f"column_count={len(self.columns)}, "
            f"row_count={self.row_count}, "
            f"truncated={self.truncated}, "
            f"elapsed_ms={self.elapsed_ms})"
        )


class DemisAdapterDiagnostics(BaseModel):
    """Internal sanitized adapter diagnostics (no host/user/DSN/credentials)."""

    model_config = ConfigDict(extra="forbid")

    configured: bool
    dbms_type: str | None = None
    live_connection_tested: bool = False
    # Only set when a future concrete adapter actually probes connectivity.
    reachable: bool | None = None
    read_only: bool | None = None
    failure_category: str | None = None

    def __repr__(self) -> str:
        return (
            "DemisAdapterDiagnostics("
            f"configured={self.configured}, "
            f"dbms_type={self.dbms_type!r}, "
            f"live_connection_tested={self.live_connection_tested}, "
            f"reachable={self.reachable}, "
            f"read_only={self.read_only}, "
            f"failure_category={self.failure_category!r})"
        )
