"""Adopt historical catalog/template tables into Alembic ownership.

Revision ID: 20261007_hist01
Revises: 20260929_audit01
Create Date: 2026-10-07

Phase 24-A: bring create_all-era tables under Alembic without destroying
existing operator data.

Tables adopted (create if missing; skip if already present):
- catalog_import_revisions
- catalog_active_revisions
- catalog_activation_events
- query_templates
- query_template_versions
- query_template_review_events

Runtime ``create_all`` is intentionally left in place by this PR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "20261007_hist01"
down_revision: str | Sequence[str] | None = "20260929_audit01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADOPTED_TABLES = (
    "catalog_import_revisions",
    "catalog_active_revisions",
    "catalog_activation_events",
    "query_templates",
    "query_template_versions",
    "query_template_review_events",
)


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def _existing_fks(table_name: str) -> set[str]:
    bind = op.get_bind()
    names: set[str] = set()
    for fk in inspect(bind).get_foreign_keys(table_name):
        name = fk.get("name")
        if name:
            names.add(name)
    return names


def upgrade() -> None:
    """Create adopted tables only when absent (legacy create_all DBs keep data)."""
    existing = _existing_tables()

    if "catalog_import_revisions" not in existing:
        op.create_table(
            "catalog_import_revisions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_name", sa.String(length=255), nullable=False),
            sa.Column("db_type", sa.String(length=64), nullable=False),
            sa.Column("database_name", sa.String(length=255), nullable=True),
            sa.Column("default_schema", sa.String(length=255), nullable=True),
            sa.Column("package_format", sa.String(length=64), nullable=False),
            sa.Column("package_version", sa.String(length=32), nullable=False),
            sa.Column("package_readiness", sa.String(length=32), nullable=False),
            sa.Column("schema_fingerprint", sa.String(length=255), nullable=False),
            sa.Column("archive_sha256", sa.String(length=64), nullable=False),
            sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
            sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column(
                "imported_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("validation_status", sa.String(length=32), nullable=False),
            sa.Column("table_count", sa.Integer(), nullable=False),
            sa.Column("column_count", sa.Integer(), nullable=False),
            sa.Column("relation_count", sa.Integer(), nullable=False),
            sa.Column("index_count", sa.Integer(), nullable=False),
            sa.Column("category_count", sa.Integer(), nullable=False),
            sa.Column("category_assignment_count", sa.Integer(), nullable=False),
            sa.Column("managed_file_count", sa.Integer(), nullable=False),
            sa.Column(
                "manifest_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "database_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "tables_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "columns_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "relations_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "indexes_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "categories_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "erd_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "latest_run_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "schema_snapshot_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "preflight_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "latest_diff_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "managed_file_digests_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "archive_sha256", name="uq_catalog_import_archive_sha256"
            ),
        )
        op.create_index(
            "ix_catalog_import_revisions_source_name",
            "catalog_import_revisions",
            ["source_name"],
            unique=False,
        )
        op.create_index(
            "ix_catalog_import_revisions_package_readiness",
            "catalog_import_revisions",
            ["package_readiness"],
            unique=False,
        )
        op.create_index(
            "ix_catalog_import_revisions_schema_fingerprint",
            "catalog_import_revisions",
            ["schema_fingerprint"],
            unique=False,
        )

    # Refresh after possible create.
    existing = _existing_tables()

    if "catalog_active_revisions" not in existing:
        op.create_table(
            "catalog_active_revisions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_name", sa.String(length=255), nullable=False),
            sa.Column("catalog_import_revision_id", sa.Integer(), nullable=False),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
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
                ondelete="RESTRICT",
                name="catalog_active_revisions_catalog_import_revision_id_fkey",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "source_name", name="uq_catalog_active_source_name"
            ),
        )
        op.create_index(
            "ix_catalog_active_revisions_source_name",
            "catalog_active_revisions",
            ["source_name"],
            unique=False,
        )
        op.create_index(
            "ix_catalog_active_revisions_catalog_import_revision_id",
            "catalog_active_revisions",
            ["catalog_import_revision_id"],
            unique=False,
        )

    if "catalog_activation_events" not in existing:
        op.create_table(
            "catalog_activation_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("source_name", sa.String(length=255), nullable=False),
            sa.Column("previous_revision_id", sa.Integer(), nullable=True),
            sa.Column("activated_revision_id", sa.Integer(), nullable=False),
            sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["previous_revision_id"],
                ["catalog_import_revisions.id"],
                ondelete="RESTRICT",
                name="catalog_activation_events_previous_revision_id_fkey",
            ),
            sa.ForeignKeyConstraint(
                ["activated_revision_id"],
                ["catalog_import_revisions.id"],
                ondelete="RESTRICT",
                name="catalog_activation_events_activated_revision_id_fkey",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_catalog_activation_events_source_name",
            "catalog_activation_events",
            ["source_name"],
            unique=False,
        )
        op.create_index(
            "ix_catalog_activation_events_previous_revision_id",
            "catalog_activation_events",
            ["previous_revision_id"],
            unique=False,
        )
        op.create_index(
            "ix_catalog_activation_events_activated_revision_id",
            "catalog_activation_events",
            ["activated_revision_id"],
            unique=False,
        )
        op.create_index(
            "ix_catalog_activation_events_activated_at",
            "catalog_activation_events",
            ["activated_at"],
            unique=False,
        )

    existing = _existing_tables()

    # Circular FK: create query_templates without current_version FK first.
    if "query_templates" not in existing:
        op.create_table(
            "query_templates",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("stable_key", sa.String(length=128), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("source_name", sa.String(length=255), nullable=False),
            sa.Column(
                "target_schemas",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("current_version_id", sa.Integer(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False),
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
                "stable_key",
                name="uq_query_templates_source_stable_key",
            ),
        )
        op.create_index(
            "ix_query_templates_source_name",
            "query_templates",
            ["source_name"],
            unique=False,
        )
        op.create_index(
            "ix_query_templates_current_version_id",
            "query_templates",
            ["current_version_id"],
            unique=False,
        )

    existing = _existing_tables()

    if "query_template_versions" not in existing:
        op.create_table(
            "query_template_versions",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("sql_text", sa.Text(), nullable=False),
            sa.Column(
                "parameter_schema",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
            ),
            sa.Column("row_limit", sa.Integer(), nullable=False),
            sa.Column("timeout_seconds", sa.Integer(), nullable=False),
            sa.Column("compatibility_mode", sa.String(length=64), nullable=False),
            sa.Column("catalog_revision_id", sa.Integer(), nullable=False),
            sa.Column(
                "catalog_fingerprint_constraint",
                sa.String(length=255),
                nullable=False,
            ),
            sa.Column("approval_status", sa.String(length=32), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column("approved_by", sa.String(length=255), nullable=True),
            sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("approval_note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["template_id"],
                ["query_templates.id"],
                ondelete="CASCADE",
                name="query_template_versions_template_id_fkey",
            ),
            sa.ForeignKeyConstraint(
                ["catalog_revision_id"],
                ["catalog_import_revisions.id"],
                ondelete="RESTRICT",
                name="query_template_versions_catalog_revision_id_fkey",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "template_id",
                "version",
                name="uq_query_template_versions_template_version",
            ),
        )
        op.create_index(
            "ix_query_template_versions_template_id",
            "query_template_versions",
            ["template_id"],
            unique=False,
        )
        op.create_index(
            "ix_query_template_versions_catalog_revision_id",
            "query_template_versions",
            ["catalog_revision_id"],
            unique=False,
        )
        op.create_index(
            "ix_query_template_versions_approval_status",
            "query_template_versions",
            ["approval_status"],
            unique=False,
        )

    # Add circular FK only when the templates table exists and the FK is absent.
    existing = _existing_tables()
    if "query_templates" in existing and "query_template_versions" in existing:
        fks = _existing_fks("query_templates")
        if "fk_query_templates_current_version_id" not in fks:
            op.create_foreign_key(
                "fk_query_templates_current_version_id",
                "query_templates",
                "query_template_versions",
                ["current_version_id"],
                ["id"],
                ondelete="RESTRICT",
            )

    existing = _existing_tables()
    if "query_template_review_events" not in existing:
        op.create_table(
            "query_template_review_events",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("template_id", sa.Integer(), nullable=False),
            sa.Column("version_id", sa.Integer(), nullable=False),
            sa.Column("from_status", sa.String(length=32), nullable=False),
            sa.Column("to_status", sa.String(length=32), nullable=False),
            sa.Column("actor", sa.String(length=255), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["template_id"],
                ["query_templates.id"],
                ondelete="CASCADE",
                name="query_template_review_events_template_id_fkey",
            ),
            sa.ForeignKeyConstraint(
                ["version_id"],
                ["query_template_versions.id"],
                ondelete="CASCADE",
                name="query_template_review_events_version_id_fkey",
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_query_template_review_events_template_id",
            "query_template_review_events",
            ["template_id"],
            unique=False,
        )
        op.create_index(
            "ix_query_template_review_events_version_id",
            "query_template_review_events",
            ["version_id"],
            unique=False,
        )
        op.create_index(
            "ix_query_template_review_events_created_at",
            "query_template_review_events",
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    """Non-destructive downgrade for historical schema adoption.

    These tables may already contain Catalog import / Query Template history
    created under ``create_all`` before Alembic ownership. Dropping them here
    would destroy operator data and violate the Phase 24-A adoption contract.

    Downgrade therefore only moves the Alembic revision pointer backward and
    intentionally retains all adopted tables/indexes/constraints listed in
    ``_ADOPTED_TABLES``.
    """
    # Explicit no-op — do not call drop_table / drop_index / drop_constraint.
    _ = _ADOPTED_TABLES
    return
