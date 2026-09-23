"""Query Template registry persistence (draft authoring; no execution path)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class QueryTemplate(Base):
    """Stable Query Template identity. Executable only after later approval PRs."""

    __tablename__ = "query_templates"
    __table_args__ = (
        UniqueConstraint("source_name", "stable_key", name="uq_query_templates_source_stable_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    stable_key: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    target_schemas: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    current_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey(
            "query_template_versions.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_query_templates_current_version_id",
        ),
        nullable=True,
        index=True,
    )

    # Templates stay disabled until a future enable/approval workflow.
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

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

    versions: Mapped[list[QueryTemplateVersion]] = relationship(
        "QueryTemplateVersion",
        back_populates="template",
        foreign_keys="QueryTemplateVersion.template_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    current_version: Mapped[QueryTemplateVersion | None] = relationship(
        "QueryTemplateVersion",
        foreign_keys=[current_version_id],
        post_update=True,
        viewonly=True,
    )


class QueryTemplateVersion(Base):
    """Immutable-ready version row. This PR only creates/updates DRAFT versions."""

    __tablename__ = "query_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_query_template_versions_template_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("query_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    version: Mapped[int] = mapped_column(Integer, nullable=False)

    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    parameter_schema: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)

    row_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    compatibility_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    catalog_revision_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("catalog_import_revisions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    catalog_fingerprint_constraint: Mapped[str] = mapped_column(String(255), nullable=False)

    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    template: Mapped[QueryTemplate] = relationship(
        "QueryTemplate",
        back_populates="versions",
        foreign_keys=[template_id],
    )


class QueryTemplateReviewEvent(Base):
    """Append-only approval lifecycle audit row (no update/delete API)."""

    __tablename__ = "query_template_review_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    template_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("query_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("query_template_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)

    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
