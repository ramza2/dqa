"""Add append-only Schema Snapshot revision history; no Catalog pointer changes.

Revision ID: 20261014_ss01
Revises: 20261008_dd02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20261014_ss01"
down_revision: str | Sequence[str] | None = "20261008_dd02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schema_snapshot_revisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("db_type", sa.String(length=64), nullable=False),
        sa.Column("database_name", sa.String(length=255), nullable=False),
        sa.Column("schema_name", sa.String(length=255), nullable=False),
        sa.Column("snapshot_version", sa.Integer(), nullable=False),
        sa.Column("schema_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("previous_revision_id", sa.Integer(), nullable=True),
        sa.Column("capture_request_id", sa.String(length=36), nullable=False),
        sa.Column("captured_by", sa.String(length=255), nullable=False),
        sa.Column("snapshot_json", JSONB(), nullable=False),
        sa.Column("counts_json", JSONB(), nullable=False),
        sa.Column("diff_summary_json", JSONB(), nullable=False),
        sa.Column(
            "captured_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["previous_revision_id"], ["schema_snapshot_revisions.id"],
            name="fk_schema_snapshot_revisions_previous_revision_id",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_name", "capture_request_id",
            name="uq_schema_snapshot_revisions_source_capture_request",
        ),
    )
    op.create_index(
        "ix_schema_snapshot_revisions_source_id",
        "schema_snapshot_revisions", ["source_name", "id"],
    )


def downgrade() -> None:
    # History is audit-sensitive: downgrade deliberately refuses destructive loss.
    raise RuntimeError(
        "Schema Snapshot revision history is immutable; no automatic destructive downgrade"
    )
