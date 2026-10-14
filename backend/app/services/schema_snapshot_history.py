"""Explicit, source-bound, append-only DQA Schema Snapshot capture service.

Not an HTTP/Oracle entrypoint. Call only after an approved metadata-only inspect
by an authenticated administrator. Caller owns the DB transaction/commit.
This does not import, update, approve, or activate a Catalog Package.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.adapters.schema_inspector.base import (
    InspectedColumn, InspectedForeignKey, InspectedForeignKeyColumn,
    InspectedIndex, InspectedIndexColumn, InspectedPrimaryKey, InspectedTable,
    InspectedUniqueConstraint, SchemaSnapshot,
)
from app.models.schema_snapshot_revision import SchemaSnapshotRevision
from app.services.schema_catalog_candidate import _fingerprint, _physical_payload
from app.services.schema_snapshot_diff import SnapshotDiff, compare_schema_snapshots

_ALLOWED_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_SNAPSHOT_VERSION = 1
_MAX_PAYLOAD_BYTES = 4_000_000
_MAX_DIFF_BYTES = 4_000_000


class SnapshotHistoryError(Exception):
    """Stable application error code; does not expose Oracle or SQL errors."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class CaptureResult:
    revision: SchemaSnapshotRevision
    created: bool


def _snapshot_from_payload(payload: dict[str, Any]) -> SchemaSnapshot:
    """Deserialize only our own sanitized v1 physical snapshot format."""
    if payload.get("snapshot_version") != _SNAPSHOT_VERSION:
        raise ValueError("unsupported snapshot version")

    def records(name: str, cls):
        value = payload[name]
        if not isinstance(value, list):
            raise ValueError("invalid snapshot records")
        return [cls(**item) for item in value]

    foreign_keys = [
        InspectedForeignKey(
            **{key: value for key, value in item.items() if key != "columns"},
            columns=tuple(InspectedForeignKeyColumn(**c) for c in item["columns"]),
        )
        for item in payload["foreign_keys"]
    ]
    indexes = [
        InspectedIndex(
            **{key: value for key, value in item.items() if key != "columns"},
            columns=tuple(InspectedIndexColumn(**c) for c in item["columns"]),
        )
        for item in payload["indexes"]
    ]
    return SchemaSnapshot(
        db_type=payload["db_type"],
        database_name=payload["database_name"],
        schema_name=payload["schema_name"],
        tables=records("tables", InspectedTable),
        columns=records("columns", InspectedColumn),
        primary_keys=records("primary_keys", InspectedPrimaryKey),
        unique_constraints=records("unique_constraints", InspectedUniqueConstraint),
        foreign_keys=foreign_keys,
        indexes=indexes,
    )


def get_snapshot_revision(
    session: Session, revision_id: int, *, source_name: str
) -> SchemaSnapshotRevision | None:
    return session.scalar(
        select(SchemaSnapshotRevision).where(
            SchemaSnapshotRevision.id == revision_id,
            SchemaSnapshotRevision.source_name == source_name,
        )
    )


def list_snapshot_revisions(
    session: Session, *, source_name: str, limit: int = 100, offset: int = 0,
) -> list[SchemaSnapshotRevision]:
    if not _ALLOWED_SOURCE.fullmatch(source_name):
        raise ValueError("invalid source_name")
    if limit < 1 or limit > 500 or offset < 0:
        raise ValueError("invalid pagination")
    return list(session.scalars(
        select(SchemaSnapshotRevision)
        .where(SchemaSnapshotRevision.source_name == source_name)
        .order_by(SchemaSnapshotRevision.id.desc())
        .limit(limit).offset(offset)
    ).all())


def capture_snapshot_revision(
    session: Session,
    snapshot: SchemaSnapshot,
    *,
    source_name: str,
    captured_by: str,
    capture_request_id: UUID,
    expected_previous_revision_id: int | None,
) -> CaptureResult:
    """Append only when expected previous revision matches the source's latest.

    PostgreSQL transaction-scoped source lock serializes first captures and
    concurrent appends. The calling transaction MUST commit before treating the
    returned revision as durable. UUID request id makes retries idempotent.
    The source and operator are trusted application inputs, never Oracle/client
    target overrides or unauthenticated HTTP request fields.
    """
    if not isinstance(source_name, str) or not _ALLOWED_SOURCE.fullmatch(source_name):
        raise SnapshotHistoryError("INVALID_SOURCE")
    if not isinstance(captured_by, str) or not captured_by.strip() or captured_by != captured_by.strip() or len(captured_by) > 255:
        raise SnapshotHistoryError("INVALID_ACTOR")
    if not isinstance(capture_request_id, UUID):
        raise SnapshotHistoryError("INVALID_CAPTURE_REQUEST_ID")
    if expected_previous_revision_id is not None and (
        not isinstance(expected_previous_revision_id, int)
        or isinstance(expected_previous_revision_id, bool)
        or expected_previous_revision_id <= 0
    ):
        raise SnapshotHistoryError("INVALID_EXPECTED_REVISION")
    if not isinstance(snapshot, SchemaSnapshot) or not snapshot.tables or not snapshot.columns:
        raise SnapshotHistoryError("INVALID_SNAPSHOT")

    try:
        # Validates duplicate object identities and key/FK/index member ordinals.
        compare_schema_snapshots(snapshot, snapshot)
        physical = _physical_payload(snapshot)
        encoded_size = len(json.dumps(physical, ensure_ascii=False).encode("utf-8"))
        if encoded_size > _MAX_PAYLOAD_BYTES:
            raise ValueError("snapshot too large")
        fp = _fingerprint(physical)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise SnapshotHistoryError("INVALID_SNAPSHOT") from None

    # Never use current active Catalog as the snapshot baseline: it is a
    # separately controlled execution authority with a different fingerprint.
    # hashtextextended collisions merely serialize independent sources.
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": "dqa:snapshot:" + source_name},
    )

    request_key = str(capture_request_id)
    existing = session.scalar(
        select(SchemaSnapshotRevision).where(
            SchemaSnapshotRevision.source_name == source_name,
            SchemaSnapshotRevision.capture_request_id == request_key,
        )
    )
    if existing is not None:
        if (
            existing.schema_fingerprint != fp
            or existing.captured_by != captured_by
            or existing.previous_revision_id != expected_previous_revision_id
            or (existing.db_type, existing.database_name, existing.schema_name)
            != (snapshot.db_type, snapshot.database_name, snapshot.schema_name)
        ):
            raise SnapshotHistoryError("CAPTURE_REQUEST_REUSED")
        return CaptureResult(existing, created=False)

    previous = session.scalar(
        select(SchemaSnapshotRevision)
        .where(SchemaSnapshotRevision.source_name == source_name)
        .order_by(SchemaSnapshotRevision.id.desc()).limit(1)
    )
    prev_id = previous.id if previous is not None else None
    if expected_previous_revision_id != prev_id:
        raise SnapshotHistoryError("STALE_SNAPSHOT_REVISION")

    if previous is not None:
        if (
            previous.snapshot_version != _SNAPSHOT_VERSION
            or (previous.db_type, previous.database_name, previous.schema_name)
            != (snapshot.db_type, snapshot.database_name, snapshot.schema_name)
        ):
            raise SnapshotHistoryError("TARGET_IDENTITY_MISMATCH")
        try:
            before = _snapshot_from_payload(previous.snapshot_json)
            if _fingerprint(_physical_payload(before)) != previous.schema_fingerprint:
                raise ValueError("corrupt fingerprint")
            diff = compare_schema_snapshots(before, snapshot)
            if diff.base_fingerprint != previous.schema_fingerprint:
                raise ValueError("corrupt baseline")
            summary = _diff_summary(diff, base_revision_id=previous.id)
        except (ValueError, TypeError, KeyError, AttributeError):
            raise SnapshotHistoryError("CORRUPT_BASELINE") from None
    else:
        summary = {
            "status": "NO_BASELINE",
            "base_revision_id": None,
            "identical": None,
            "total_changes": None,
            "counts": {},
            "changes": [],
        }

    if len(json.dumps(summary, ensure_ascii=False).encode("utf-8")) > _MAX_DIFF_BYTES:
        raise SnapshotHistoryError("DIFF_TOO_LARGE")

    row = SchemaSnapshotRevision(
        source_name=source_name,
        db_type=snapshot.db_type,
        database_name=snapshot.database_name,
        schema_name=snapshot.schema_name,
        snapshot_version=_SNAPSHOT_VERSION,
        schema_fingerprint=fp,
        previous_revision_id=prev_id,
        capture_request_id=request_key,
        captured_by=captured_by,
        snapshot_json=physical,
        counts_json={
            "tables": len(snapshot.tables),
            "columns": len(snapshot.columns),
            "primary_key_columns": len(snapshot.primary_keys),
            "unique_key_columns": len(snapshot.unique_constraints),
            "foreign_keys": len(snapshot.foreign_keys),
            "indexes": len(snapshot.indexes),
        },
        diff_summary_json=summary,
    )
    session.add(row)
    session.flush()
    return CaptureResult(row, created=True)


def _diff_summary(diff: SnapshotDiff, *, base_revision_id: int) -> dict[str, Any]:
    return {
        "status": "COMPARED",
        "base_revision_id": base_revision_id,
        "base_fingerprint": diff.base_fingerprint,
        "identical": diff.identical,
        "total_changes": diff.total_changes,
        "counts": {
            name: {
                "added": count.added,
                "removed": count.removed,
                "changed": count.changed,
            }
            for name, count in diff.counts.items()
        },
        "changes": [
            {
                "object_type": item.object_type,
                "change_type": item.change_type,
                "object_key": list(item.object_key),
                "changed_fields": list(item.changed_fields),
            }
            for item in diff.changes
        ],
    }
