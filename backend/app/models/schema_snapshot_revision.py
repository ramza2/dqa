"""Append-only metadata Snapshot captures; never active Catalog authority."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SchemaSnapshotRevision(Base):
    """Captured physical metadata and predecessor, distinct from Catalog imports."""

    __tablename__ = "schema_snapshot_revisions"
    __table_args__ = (
        UniqueConstraint(
            "source_name", "capture_request_id",
            name="uq_schema_snapshot_revisions_source_capture_request",
        ),
        Index(
            "ix_schema_snapshot_revisions_source_id",
            "source_name", "id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    db_type: Mapped[str] = mapped_column(String(64), nullable=False)
    database_name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_revision_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("schema_snapshot_revisions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    capture_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    captured_by: Mapped[str] = mapped_column(String(255), nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    counts_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    diff_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
