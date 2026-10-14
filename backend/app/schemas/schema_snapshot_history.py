"""Public history metadata only; never expose raw Snapshot JSON."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


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
