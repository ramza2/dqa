"""M5-S1A non-authorizing service-client policy drafts and append-only audit."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ServiceClientDraft(Base):
    __tablename__ = "service_client_drafts"
    __table_args__ = (
        UniqueConstraint("client_id", name="uq_service_client_drafts_client_id"),
        CheckConstraint("status IN ('DRAFT', 'REVOKED')", name="ck_service_client_drafts_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False)
    service_name: Mapped[str] = mapped_column(String(128), nullable=False)
    organization: Mapped[str] = mapped_column(String(128), nullable=False)
    owner_contact: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    proposed_ip_cidrs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ServiceClientDraftEvent(Base):
    """Append-only policy change marker; never contains credentials or request bodies."""

    __tablename__ = "service_client_draft_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_draft_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("service_client_drafts.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
