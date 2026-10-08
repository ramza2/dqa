"""Revision-scoped Data Discovery search document persistence (Phase 27-A).

Derived from immutable CatalogImportRevision JSON. Activation is not stored
here — CatalogActiveRevision remains the sole active pointer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DataDiscoveryDocument(Base):
    """One TABLE/COLUMN search document for a single Catalog import revision."""

    __tablename__ = "data_discovery_documents"
    __table_args__ = (
        UniqueConstraint(
            "catalog_import_revision_id",
            "document_key",
            name="uq_data_discovery_documents_revision_document_key",
        ),
        Index(
            "ix_data_discovery_documents_revision_object_type",
            "catalog_import_revision_id",
            "object_type",
        ),
        Index(
            "ix_data_discovery_documents_source_revision",
            "source_name",
            "catalog_import_revision_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    catalog_import_revision_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("catalog_import_revisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    schema_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    object_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    identity_kind: Mapped[str] = mapped_column(String(32), nullable=False)

    schema_name: Mapped[str] = mapped_column(String(255), nullable=False)
    table_name: Mapped[str] = mapped_column(String(255), nullable=False)
    column_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    document_key: Mapped[str] = mapped_column(String(512), nullable=False)
    searchable_text: Mapped[str] = mapped_column(Text, nullable=False)

    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    document_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    builder_version: Mapped[str] = mapped_column(String(32), nullable=False)

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
