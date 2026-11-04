"""Opt-in local operator authentication with revocable opaque sessions.

Revision ID: 20261104_auth01
Revises: 20261030_m5s1a
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20261104_auth01"
down_revision: str | Sequence[str] | None = "20261030_m5s1a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "local_auth_users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "local_auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("local_auth_users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("token_sha256", name="uq_local_auth_sessions_token_sha256"),
    )
    op.create_index("ix_local_auth_sessions_user_id", "local_auth_sessions", ["user_id"])


def downgrade() -> None:
    raise RuntimeError("Local account/session audit state must not be silently deleted")
