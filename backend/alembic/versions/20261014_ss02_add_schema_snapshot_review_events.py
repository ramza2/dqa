"""Append-only administrator Snapshot change-review events, not preflight approval.

Revision ID: 20261014_ss02
Revises: 20261014_ss01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261014_ss02"
down_revision: str | Sequence[str] | None = "20261014_ss01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schema_snapshot_review_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_name", sa.String(255), nullable=False),
        sa.Column("snapshot_revision_id", sa.Integer(), nullable=False),
        sa.Column("schema_fingerprint", sa.String(64), nullable=False),
        sa.Column("review_request_id", sa.String(36), nullable=False),
        sa.Column("previous_review_event_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(255), nullable=False),
        sa.Column(
            "reviewed_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["snapshot_revision_id"], ["schema_snapshot_revisions.id"],
            name="fk_schema_review_events_snapshot_revision", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_review_event_id"], ["schema_snapshot_review_events.id"],
            name="fk_schema_review_events_previous_event", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "source_name", "review_request_id",
            name="uq_schema_review_events_source_request",
        ),
        sa.CheckConstraint(
            "decision IN ('ACKNOWLEDGED', 'CHANGES_REQUESTED')",
            name="ck_schema_review_events_decision",
        ),
        sa.CheckConstraint(
            "reason_code IN ('REVIEWED_CHANGES', 'RECHECK_REQUIRED', 'SCOPE_UNCLEAR')",
            name="ck_schema_review_events_reason",
        ),
    )
    op.create_index(
        "ix_schema_review_events_source_revision_id",
        "schema_snapshot_review_events",
        ["source_name", "snapshot_revision_id", "id"],
    )


def downgrade() -> None:
    raise RuntimeError(
        "Schema change-review audit events are append-only; destructive downgrade disabled"
    )
