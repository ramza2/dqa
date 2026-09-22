"""Immutable Catalog Package import revision persistence model."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CatalogImportRevision(Base):
    """One immutable import of a validated Catalog Package v2 archive.

    Activation state is intentionally not stored here. Future Active Catalog
    management should reference these rows via a separate pointer/history model.
    """

    __tablename__ = "catalog_import_revisions"
    __table_args__ = (
        UniqueConstraint("archive_sha256", name="uq_catalog_import_archive_sha256"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    db_type: Mapped[str] = mapped_column(String(64), nullable=False)
    database_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_schema: Mapped[str | None] = mapped_column(String(255), nullable=True)

    package_format: Mapped[str] = mapped_column(String(64), nullable=False)
    package_version: Mapped[str] = mapped_column(String(32), nullable=False)
    package_readiness: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    schema_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    validation_status: Mapped[str] = mapped_column(String(32), nullable=False, default="VALID")

    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    column_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    index_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category_assignment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    managed_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    database_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tables_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    columns_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    relations_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    indexes_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    categories_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    erd_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    latest_run_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    schema_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    preflight_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    latest_diff_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Optional digest map for managed files (path -> sha256); not exposed by default APIs.
    managed_file_digests_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
