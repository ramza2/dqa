"""add data_discovery_embeddings table and vector extension

Revision ID: 20261008_dd02
Revises: 20261008_dd01
Create Date: 2026-10-08

Phase 27-B: revision-scoped embedding persistence for Data Discovery semantic
search. Creates the ``vector`` extension when missing. Downgrade drops only
the embeddings table and leaves the extension installed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "20261008_dd02"
down_revision: str | Sequence[str] | None = "20261008_dd01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.create_table(
        "data_discovery_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("data_discovery_document_id", sa.Integer(), nullable=False),
        sa.Column("model_key", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("model_revision", sa.String(length=128), nullable=True),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("normalized", sa.Boolean(), nullable=False),
        sa.Column("document_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
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
            ["data_discovery_document_id"],
            ["data_discovery_documents.id"],
            name="fk_data_discovery_embeddings_document_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "data_discovery_document_id",
            "model_key",
            name="uq_data_discovery_embeddings_document_model_key",
        ),
    )
    op.create_index(
        "ix_data_discovery_embeddings_document_id",
        "data_discovery_embeddings",
        ["data_discovery_document_id"],
    )
    op.create_index(
        "ix_data_discovery_embeddings_model_key",
        "data_discovery_embeddings",
        ["model_key"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_data_discovery_embeddings_model_key",
        table_name="data_discovery_embeddings",
    )
    op.drop_index(
        "ix_data_discovery_embeddings_document_id",
        table_name="data_discovery_embeddings",
    )
    op.drop_table("data_discovery_embeddings")
    # Intentionally do not DROP EXTENSION vector — other objects may depend on it.
