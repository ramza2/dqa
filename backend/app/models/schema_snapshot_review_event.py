"""Append-only review decisions for physical Schema Snapshots.

Decisions explicitly do NOT constitute independent DBA preflight, Catalog
readiness or activation authority.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, Integer, String,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SchemaSnapshotReviewEvent(Base):
    __tablename__ = "schema_snapshot_review_events"
    __table_args__ = (
        UniqueConstraint(
            "source_name", "review_request_id",
            name="uq_schema_review_events_source_request",
        ),
        CheckConstraint(
            "decision IN ('ACKNOWLEDGED', 'CHANGES_REQUESTED')",
            name="ck_schema_review_events_decision",
        ),
        CheckConstraint(
            "reason_code IN ('REVIEWED_CHANGES', 'RECHECK_REQUIRED', 'SCOPE_UNCLEAR')",
            name="ck_schema_review_events_reason",
        ),
        Index(
            "ix_schema_review_events_source_revision_id",
            "source_name", "snapshot_revision_id", "id",
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_revision_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("schema_snapshot_revisions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    review_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    previous_review_event_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("schema_snapshot_review_events.id", ondelete="RESTRICT"),
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
