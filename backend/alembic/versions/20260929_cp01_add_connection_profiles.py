"""add connection_profiles table

Revision ID: 20260929_cp01
Revises:
Create Date: 2026-09-29

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260929_cp01"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connection_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dbms_type", sa.String(length=64), nullable=True),
        sa.Column("host", sa.String(length=255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("database_name", sa.String(length=255), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("credential_secret_ref", sa.String(length=512), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_name",
            "environment",
            name="uq_connection_profiles_source_environment",
        ),
    )
    op.create_index(
        "ix_connection_profiles_source_name",
        "connection_profiles",
        ["source_name"],
        unique=False,
    )
    op.create_index(
        "ix_connection_profiles_environment",
        "connection_profiles",
        ["environment"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_connection_profiles_environment", table_name="connection_profiles")
    op.drop_index("ix_connection_profiles_source_name", table_name="connection_profiles")
    op.drop_table("connection_profiles")
