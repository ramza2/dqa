"""S-04-C-2B-1: append-only, administrator-requested change-review audit.

ACKNOWLEDGED means a human inspected the Snapshot changes. Neither decision
certifies independent metadata preflight nor confers Catalog READY eligibility.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.schema_snapshot_review_event import SchemaSnapshotReviewEvent
from app.services.schema_snapshot_review import (
    SnapshotReviewError,
    preview_snapshot_review,
)
from app.services.schema_snapshot_history import get_snapshot_revision

_ALLOWED_SOURCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_ALLOWED_FP = re.compile(r"^[0-9a-f]{64}$")


class SnapshotReviewEventError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ReviewEventResult:
    event: SchemaSnapshotReviewEvent
    created: bool


def list_review_events(
    session: Session, *, source_name: str, snapshot_revision_id: int,
) -> list[SchemaSnapshotReviewEvent]:
    if not _ALLOWED_SOURCE.fullmatch(source_name):
        raise SnapshotReviewEventError("INVALID_SOURCE")
    if get_snapshot_revision(session, snapshot_revision_id, source_name=source_name) is None:
        raise SnapshotReviewEventError("SNAPSHOT_REVISION_NOT_FOUND")
    return list(session.scalars(
        select(SchemaSnapshotReviewEvent)
        .where(
            SchemaSnapshotReviewEvent.source_name == source_name,
            SchemaSnapshotReviewEvent.snapshot_revision_id == snapshot_revision_id,
        ).order_by(SchemaSnapshotReviewEvent.id.desc()).limit(100)
    ).all())


def record_review_event(
    session: Session,
    *,
    source_name: str,
    snapshot_revision_id: int,
    expected_schema_fingerprint: str,
    review_request_id: UUID,
    expected_previous_review_event_id: int | None,
    decision: str,
    reason_code: str,
    reviewed_by: str,
) -> ReviewEventResult:
    """Serialize against capture and review; persist a narrowly scoped decision.

    This operation commits before success and never imports/activates Catalog.
    Idempotent replay of an identical request is permitted after a newer
    Snapshot, but any *new* decision on an old Snapshot fails closed.
    """
    if not isinstance(source_name, str) or not _ALLOWED_SOURCE.fullmatch(source_name):
        raise SnapshotReviewEventError("INVALID_SOURCE")
    if not isinstance(expected_schema_fingerprint, str) or not _ALLOWED_FP.fullmatch(
        expected_schema_fingerprint
    ):
        raise SnapshotReviewEventError("INVALID_FINGERPRINT")
    if not isinstance(review_request_id, UUID):
        raise SnapshotReviewEventError("INVALID_REQUEST_ID")
    if (
        not isinstance(reviewed_by, str)
        or not reviewed_by.strip()
        or reviewed_by != reviewed_by.strip()
        or len(reviewed_by) > 255
    ):
        raise SnapshotReviewEventError("INVALID_ACTOR")
    if (
        decision not in ("ACKNOWLEDGED", "CHANGES_REQUESTED")
        or (decision == "ACKNOWLEDGED" and reason_code != "REVIEWED_CHANGES")
        or (
            decision == "CHANGES_REQUESTED"
            and reason_code not in ("RECHECK_REQUIRED", "SCOPE_UNCLEAR")
        )
    ):
        raise SnapshotReviewEventError("INVALID_DECISION")
    if expected_previous_review_event_id is not None and (
        isinstance(expected_previous_review_event_id, bool)
        or not isinstance(expected_previous_review_event_id, int)
        or expected_previous_review_event_id <= 0
    ):
        raise SnapshotReviewEventError("INVALID_PREDECESSOR")

    try:
        # Same source-scoped lock as Snapshot capture prevents review/capture
        # races, including under READ COMMITTED transaction isolation.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": "dqa:snapshot:" + source_name},
        )
        key = str(review_request_id)
        replay = session.scalar(
            select(SchemaSnapshotReviewEvent).where(
                SchemaSnapshotReviewEvent.source_name == source_name,
                SchemaSnapshotReviewEvent.review_request_id == key,
            )
        )
        if replay is not None:
            if (
                replay.snapshot_revision_id != snapshot_revision_id
                or replay.schema_fingerprint != expected_schema_fingerprint
                or replay.previous_review_event_id != expected_previous_review_event_id
                or replay.decision != decision
                or replay.reason_code != reason_code
                or replay.reviewed_by != reviewed_by
            ):
                raise SnapshotReviewEventError("REVIEW_REQUEST_REUSED")
            session.commit()
            return ReviewEventResult(event=replay, created=False)

        try:
            preview = preview_snapshot_review(
                session, source_name=source_name, revision_id=snapshot_revision_id,
            )
        except SnapshotReviewError as exc:
            raise SnapshotReviewEventError(exc.code) from None

        if not preview.is_latest:
            raise SnapshotReviewEventError("STALE_SNAPSHOT_REVISION")
        if preview.schema_fingerprint != expected_schema_fingerprint:
            raise SnapshotReviewEventError("STALE_SNAPSHOT_FINGERPRINT")

        predecessor = session.scalar(
            select(SchemaSnapshotReviewEvent)
            .where(
                SchemaSnapshotReviewEvent.source_name == source_name,
                SchemaSnapshotReviewEvent.snapshot_revision_id == snapshot_revision_id,
            ).order_by(SchemaSnapshotReviewEvent.id.desc()).limit(1)
        )
        prev_id = predecessor.id if predecessor is not None else None
        if prev_id != expected_previous_review_event_id:
            raise SnapshotReviewEventError("STALE_REVIEW_EVENT")

        row = SchemaSnapshotReviewEvent(
            source_name=source_name,
            snapshot_revision_id=snapshot_revision_id,
            schema_fingerprint=preview.schema_fingerprint,
            review_request_id=key,
            previous_review_event_id=prev_id,
            decision=decision,
            reason_code=reason_code,
            reviewed_by=reviewed_by,
        )
        session.add(row)
        session.flush()
        session.commit()
        return ReviewEventResult(event=row, created=True)
    except Exception:
        session.rollback()
        raise
