"""add query_audit_events table

Revision ID: 20260929_audit01
Revises: 20260929_cp01
Create Date: 2026-09-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260929_audit01"
down_revision: str | Sequence[str] | None = "20260929_cp01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "query_audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("audit_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("catalog_revision_id", sa.Integer(), nullable=True),
        sa.Column("catalog_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("template_version_id", sa.Integer(), nullable=True),
        sa.Column("connection_profile_id", sa.Integer(), nullable=True),
        sa.Column(
            "parameter_names",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "sensitive_parameter_names",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "parameter_logging_policy",
            sa.String(length=32),
            nullable=False,
            server_default="NAMES_ONLY",
        ),
        sa.Column("failure_category", sa.String(length=64), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=True),
        sa.Column("result_truncated", sa.Boolean(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_query_audit_events_audit_id", "query_audit_events", ["audit_id"])
    op.create_index(
        "ix_query_audit_events_event_type", "query_audit_events", ["event_type"]
    )
    op.create_index("ix_query_audit_events_status", "query_audit_events", ["status"])
    op.create_index("ix_query_audit_events_actor_id", "query_audit_events", ["actor_id"])
    op.create_index(
        "ix_query_audit_events_source_name", "query_audit_events", ["source_name"]
    )
    op.create_index(
        "ix_query_audit_events_template_id", "query_audit_events", ["template_id"]
    )
    op.create_index(
        "ix_query_audit_events_created_at", "query_audit_events", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_query_audit_events_created_at", table_name="query_audit_events")
    op.drop_index("ix_query_audit_events_template_id", table_name="query_audit_events")
    op.drop_index("ix_query_audit_events_source_name", table_name="query_audit_events")
    op.drop_index("ix_query_audit_events_actor_id", table_name="query_audit_events")
    op.drop_index("ix_query_audit_events_status", table_name="query_audit_events")
    op.drop_index("ix_query_audit_events_event_type", table_name="query_audit_events")
    op.drop_index("ix_query_audit_events_audit_id", table_name="query_audit_events")
    op.drop_table("query_audit_events")
