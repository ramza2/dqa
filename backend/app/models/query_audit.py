"""Append-only Query Audit Event persistence (no secrets / values / result rows)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QueryAuditEvent(Base):
    """Immutable audit snapshot for query request/execution metadata.

    Identifiers are stored as plain values (no FK cascade). Parameter *values*,
    SQL text, result rows, and credentials are never stored.
    """

    __tablename__ = "query_audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Application-generated correlation id shared across related append-only rows.
    audit_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    actor_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Immutable historical references — not FK-coupled to lifecycle tables.
    catalog_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    catalog_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    template_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    template_version_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    connection_profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Names only (NAMES_ONLY policy). Never values.
    parameter_names: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    sensitive_parameter_names: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    parameter_logging_policy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NAMES_ONLY"
    )

    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Short truncation indicator only (e.g. "truncated"); never result payload.
    result_truncated: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
