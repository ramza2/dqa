"""S-04-C-2A read-only verification of an immutable Snapshot and Catalog candidate.

This is a *review preview*, never independent Oracle/DBA preflight evidence.
It does not approve, persist, import, activate, or mark a package READY.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.services.catalog_package_validation import validate_catalog_package_bytes
from app.services.schema_catalog_candidate import (
    _fingerprint, _physical_payload, build_catalog_v2_candidate,
)
from app.services.schema_snapshot_diff import compare_schema_snapshots
from app.services.schema_snapshot_history import (
    _diff_summary,
    _snapshot_from_payload,
    get_snapshot_revision,
    list_snapshot_revisions,
)

REQUIRED_GATES: tuple[str, ...] = (
    "MANUAL_CHANGE_REVIEW",
    "INDEPENDENT_PREFLIGHT",
    "EXPLICIT_CATALOG_IMPORT",
    "READY_ELIGIBILITY_VERIFICATION",
    "MANUAL_ACTIVATION",
)


class SnapshotReviewError(Exception):
    """Stable sanitized error codes, not database or metadata exception bodies."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SnapshotReviewPreview:
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


def preview_snapshot_review(
    session: Session,
    *,
    source_name: str,
    revision_id: int,
) -> SnapshotReviewPreview:
    """Verify stored metadata & v2 candidate; return no approval or new records."""
    row = get_snapshot_revision(session, revision_id, source_name=source_name)
    if row is None:
        raise SnapshotReviewError("SNAPSHOT_REVISION_NOT_FOUND")
    try:
        latest = list_snapshot_revisions(session, source_name=source_name, limit=1)
        if not latest or latest[0].id < row.id:
            raise ValueError("invalid history order")
        if row.snapshot_version != 1:
            raise ValueError("unsupported snapshot version")

        snapshot = _snapshot_from_payload(row.snapshot_json)
        if (
            (snapshot.db_type, snapshot.database_name, snapshot.schema_name)
            != (row.db_type, row.database_name, row.schema_name)
        ):
            raise ValueError("stored snapshot target mismatch")
        # The same validator used at capture rejects duplicate identities and
        # invalid ordered FK, PK, UK and index mappings.
        compare_schema_snapshots(snapshot, snapshot)
        if _fingerprint(_physical_payload(snapshot)) != row.schema_fingerprint:
            raise ValueError("stored snapshot digest mismatch")
        if row.counts_json != {
            "tables": len(snapshot.tables),
            "columns": len(snapshot.columns),
            "primary_key_columns": len(snapshot.primary_keys),
            "unique_key_columns": len(snapshot.unique_constraints),
            "foreign_keys": len(snapshot.foreign_keys),
            "indexes": len(snapshot.indexes),
        }:
            raise ValueError("stored snapshot counts mismatch")

        if row.previous_revision_id is None:
            expected_diff = {
                "status": "NO_BASELINE",
                "base_revision_id": None,
                "identical": None,
                "total_changes": None,
                "counts": {},
                "changes": [],
            }
        else:
            previous = get_snapshot_revision(
                session, row.previous_revision_id, source_name=source_name,
            )
            if previous is None or previous.id >= row.id or previous.snapshot_version != 1:
                raise ValueError("invalid previous revision")
            old = _snapshot_from_payload(previous.snapshot_json)
            if (
                (old.db_type, old.database_name, old.schema_name)
                != (previous.db_type, previous.database_name, previous.schema_name)
            ):
                raise ValueError("previous target mismatch")
            compare_schema_snapshots(old, old)
            if _fingerprint(_physical_payload(old)) != previous.schema_fingerprint:
                raise ValueError("previous snapshot digest mismatch")
            expected_diff = _diff_summary(
                compare_schema_snapshots(old, snapshot),
                base_revision_id=previous.id,
            )
        if row.diff_summary_json != expected_diff:
            raise ValueError("stored diff summary mismatch")

        # Check the same v2 validator as the existing Catalog import route.
        # This candidate is ephemeral and deliberately WARNING; it cannot be
        # upgraded to READY here, even when the Snapshot is identical.
        candidate = build_catalog_v2_candidate(
            snapshot,
            source_name=source_name,
            generated_at=row.captured_at,
        )
        validated = validate_catalog_package_bytes(candidate)
        if (
            validated.schema_fingerprint != row.schema_fingerprint
            or validated.source.source_name != row.source_name
            or validated.source.database_name != row.database_name
            or validated.source.default_schema != row.schema_name
            or validated.package_readiness != "WARNING"
            or validated.activation_eligible
        ):
            raise ValueError("invalid offline candidate")
    except Exception:
        # Stored metadata and validator errors must never leak details to HTTP
        # clients or be construed as positive preflight/READY decisions.
        raise SnapshotReviewError("SNAPSHOT_REVIEW_UNVERIFIABLE") from None

    return SnapshotReviewPreview(
        source_name=source_name,
        revision_id=row.id,
        latest_revision_id=latest[0].id,
        is_latest=latest[0].id == row.id,
        schema_fingerprint=row.schema_fingerprint,
        captured_at=row.captured_at,
        review_status="REVIEW_REQUIRED" if latest[0].id == row.id else "SUPERSEDED",
        diff_status=expected_diff["status"],
        identical=expected_diff["identical"],
        total_changes=expected_diff["total_changes"],
        snapshot_verified=True,
        candidate_package_valid=True,
        candidate_package_readiness="WARNING",
        preflight_status="NOT_VERIFIED",
        activation_eligible=False,
        required_gates=REQUIRED_GATES,
    )
