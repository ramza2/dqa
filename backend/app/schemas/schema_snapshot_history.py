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


class SchemaSnapshotReviewPreview(BaseModel):
    """Read-only verification of stored Snapshot and offline WARNING candidate.

    A successful preview is *not* independent DBA/Oracle preflight or review
    approval. It never authorizes an import or activation.
    """

    source_name: str
    revision_id: int
    latest_revision_id: int
    is_latest: bool
    schema_fingerprint: str
    captured_at: datetime
    review_status: Literal["REVIEW_REQUIRED", "SUPERSEDED"]
    diff_status: Literal["NO_BASELINE", "COMPARED"]
    identical: bool | None
    total_changes: int | None
    snapshot_verified: bool
    candidate_package_valid: bool
    candidate_package_readiness: Literal["WARNING"]
    preflight_status: Literal["NOT_VERIFIED"]
    activation_eligible: Literal[False]
    required_gates: tuple[str, ...]


class SnapshotChangeReviewRequest(BaseModel):
    """Administrator's manual change-review event, NOT Catalog approval.

    No arbitrary comments/evidence/role/actor permitted in client payload.
    """

    model_config = ConfigDict(extra="forbid")

    review_request_id: UUID
    expected_schema_fingerprint: str = Field(
        min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$",
    )
    expected_previous_review_event_id: int | None = Field(..., ge=1)
    decision: Literal["ACKNOWLEDGED", "CHANGES_REQUESTED"]
    reason_code: Literal["REVIEWED_CHANGES", "RECHECK_REQUIRED", "SCOPE_UNCLEAR"]


class SnapshotChangeReviewEventResponse(BaseModel):
    id: int
    source_name: str
    snapshot_revision_id: int
    schema_fingerprint: str
    previous_review_event_id: int | None
    decision: Literal["ACKNOWLEDGED", "CHANGES_REQUESTED"]
    reason_code: Literal["REVIEWED_CHANGES", "RECHECK_REQUIRED", "SCOPE_UNCLEAR"]
    reviewed_by: str
    reviewed_at: datetime
    created: bool | None = None
    independent_preflight_verified: Literal[False] = False
    catalog_ready: Literal[False] = False
    catalog_activated: Literal[False] = False


class SnapshotErdTable(BaseModel):
    schema_name: str
    table_name: str


class SnapshotErdColumnMapping(BaseModel):
    source: str
    target: str


class SnapshotErdEdge(BaseModel):
    direction: Literal["IN", "OUT"]
    constraint_name: str
    source_schema: str
    source_table: str
    target_schema: str
    target_table: str
    referenced_only: bool
    column_mapping: list[SnapshotErdColumnMapping]


class SnapshotErdResponse(BaseModel):
    """Sanitized ERD preview only. Never a raw snapshot or approval."""
    source_name: str
    revision_id: int
    schema_fingerprint: str
    preflight_status: Literal["NOT_VERIFIED"]
    activation_eligible: Literal[False]
    total_tables: int
    offset: int
    limit: int
    tables: list[SnapshotErdTable]
    focus_schema: str | None
    focus_table: str | None
    total_edges: int
    edges_truncated: bool
    edges: list[SnapshotErdEdge]
