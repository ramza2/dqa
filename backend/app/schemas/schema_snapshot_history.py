"""Public history metadata only; never expose raw Snapshot JSON."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SchemaSnapshotRevisionSummary(BaseModel):
    id: int
    source_name: str
    db_type: str
    database_name: str
    schema_name: str
    schema_fingerprint: str
    previous_revision_id: int | None
    captured_by: str
    captured_at: datetime
    counts: dict[str, int]
    diff_status: Literal["NO_BASELINE", "COMPARED"]
    total_changes: int | None


class SchemaSnapshotRevisionDetail(SchemaSnapshotRevisionSummary):
    diff_counts: dict[str, dict[str, int]]
    changes: list[dict[str, Any]]

class SchemaSnapshotCaptureRequest(BaseModel):
    """Explicit CAS + idempotency only. No source/schema/SQL/credentials."""

    model_config = ConfigDict(extra="forbid")

    capture_request_id: UUID
    expected_previous_revision_id: int | None = Field(..., ge=1)


class SchemaSnapshotCaptureResponse(SchemaSnapshotRevisionSummary):
    status: Literal["CAPTURED"] = "CAPTURED"
    created: bool
    imported: Literal[False] = False
    activated: Literal[False] = False
