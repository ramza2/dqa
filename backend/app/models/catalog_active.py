"""Active Catalog pointer and activation audit models.

CatalogImportRevision rows remain immutable. Activation state lives only in
CatalogActiveRevision (current pointer per source) and CatalogActivationEvent
(append-only history).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CatalogActiveRevision(Base):
    """Current active Catalog import revision pointer for one source_name."""

    __tablename__ = "catalog_active_revisions"
    __table_args__ = (
        UniqueConstraint("source_name", name="uq_catalog_active_source_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    catalog_import_revision_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("catalog_import_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CatalogActivationEvent(Base):
    """Append-only activation / revision-switch audit row (no actor yet)."""

    __tablename__ = "catalog_activation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    previous_revision_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("catalog_import_revisions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    activated_revision_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("catalog_import_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
