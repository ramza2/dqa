"""M5-S1A service client policy drafts: never grants external access.

Revision ID: 20261030_m5s1a
Revises: 20261014_ss02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261030_m5s1a"
down_revision: str | Sequence[str] | None = "20261014_ss02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "service_client_drafts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("client_id", sa.String(64), nullable=False),
        sa.Column("service_name", sa.String(128), nullable=False),
        sa.Column("organization", sa.String(128), nullable=False),
        sa.Column("owner_contact", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(16), nullable=False),
        sa.Column("requested_scopes", sa.JSON(), nullable=False),
        sa.Column("proposed_ip_cidrs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("client_id", name="uq_service_client_drafts_client_id"),
        sa.CheckConstraint("status IN ('DRAFT', 'REVOKED')", name="ck_service_client_drafts_status"),
    )
    op.create_table(
        "service_client_draft_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("client_draft_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("changed_fields", sa.JSON(), nullable=False),
        sa.Column("policy_sha256", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["client_draft_id"], ["service_client_drafts.id"],
            name="fk_service_client_draft_events_client", ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_service_client_draft_events_client_id",
        "service_client_draft_events", ["client_draft_id", "id"],
    )


def downgrade() -> None:
    raise RuntimeError("Service client policy draft history is append-only; destructive downgrade disabled")
