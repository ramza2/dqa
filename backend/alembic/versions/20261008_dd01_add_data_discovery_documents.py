"""add data_discovery_documents table

Revision ID: 20261008_dd01
Revises: 20261007_hist01
Create Date: 2026-10-08

Phase 27-A: revision-scoped Data Discovery search document persistence.
No pgvector extension, embedding columns, or historical-table changes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261008_dd01"
down_revision: str | Sequence[str] | None = "20261007_hist01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_discovery_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("catalog_import_revision_id", sa.Integer(), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("schema_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("object_type", sa.String(length=32), nullable=False),
        sa.Column("identity_kind", sa.String(length=32), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("table_name", sa.String(length=255), nullable=False),
        sa.Column("column_name", sa.String(length=255), nullable=True),
        sa.Column("document_key", sa.String(length=512), nullable=False),
        sa.Column("searchable_text", sa.Text(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("document_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("builder_version", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["catalog_import_revision_id"],
            ["catalog_import_revisions.id"],
            name="fk_data_discovery_documents_catalog_import_revision_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "catalog_import_revision_id",
            "document_key",
            name="uq_data_discovery_documents_revision_document_key",
        ),
    )
    op.create_index(
        "ix_data_discovery_documents_catalog_import_revision_id",
        "data_discovery_documents",
        ["catalog_import_revision_id"],
    )
    op.create_index(
        "ix_data_discovery_documents_source_name",
        "data_discovery_documents",
        ["source_name"],
    )
    op.create_index(
        "ix_data_discovery_documents_schema_fingerprint",
        "data_discovery_documents",
        ["schema_fingerprint"],
    )
    op.create_index(
        "ix_data_discovery_documents_object_type",
        "data_discovery_documents",
        ["object_type"],
    )
    op.create_index(
        "ix_data_discovery_documents_revision_object_type",
        "data_discovery_documents",
        ["catalog_import_revision_id", "object_type"],
    )
    op.create_index(
        "ix_data_discovery_documents_source_revision",
        "data_discovery_documents",
        ["source_name", "catalog_import_revision_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_discovery_documents_source_revision",
        table_name="data_discovery_documents",
    )
    op.drop_index(
        "ix_data_discovery_documents_revision_object_type",
        table_name="data_discovery_documents",
    )
    op.drop_index(
        "ix_data_discovery_documents_object_type",
        table_name="data_discovery_documents",
    )
    op.drop_index(
        "ix_data_discovery_documents_schema_fingerprint",
        table_name="data_discovery_documents",
    )
    op.drop_index(
        "ix_data_discovery_documents_source_name",
        table_name="data_discovery_documents",
    )
    op.drop_index(
        "ix_data_discovery_documents_catalog_import_revision_id",
        table_name="data_discovery_documents",
    )
    op.drop_table("data_discovery_documents")
