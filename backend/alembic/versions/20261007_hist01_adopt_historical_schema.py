"""Adopt historical catalog/template tables into Alembic ownership.

Revision ID: 20261007_hist01
Revises: 20260929_audit01
Create Date: 2026-10-07

Phase 24-A: bring create_all-era tables under Alembic without destroying
existing operator data.

Tables adopted (create if missing; adopt only when schema-compatible):
- catalog_import_revisions
- catalog_active_revisions
- catalog_activation_events
- query_templates
- query_template_versions
- query_template_review_events

Existing tables are never ALTER/repair/drop/recreated by this revision.
Incompatible legacy schemas fail closed before the revision is stamped.
Runtime ``create_all`` is intentionally left in place by this PR.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

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

# Expected schema contracts for adoption compatibility / fresh-create parity.
# Types use coarse families that inspector can validate safely across PG versions.
_Col = dict[str, Any]
_Schema = dict[str, Any]


def _col(family: str, *, nullable: bool, length: int | None = None) -> _Col:
    spec: _Col = {"family": family, "nullable": nullable}
    if length is not None:
        spec["length"] = length
    return spec


_EXPECTED: dict[str, _Schema] = {
    "catalog_import_revisions": {
        "pk": ["id"],
        "columns": {
            "id": _col("integer", nullable=False),
            "source_name": _col("varchar", nullable=False, length=255),
            "db_type": _col("varchar", nullable=False, length=64),
            "database_name": _col("varchar", nullable=True, length=255),
            "default_schema": _col("varchar", nullable=True, length=255),
            "package_format": _col("varchar", nullable=False, length=64),
            "package_version": _col("varchar", nullable=False, length=32),
            "package_readiness": _col("varchar", nullable=False, length=32),
            "schema_fingerprint": _col("varchar", nullable=False, length=255),
            "archive_sha256": _col("varchar", nullable=False, length=64),
            "manifest_sha256": _col("varchar", nullable=False, length=64),
            "generated_at": _col("timestamptz", nullable=False),
            "imported_at": _col("timestamptz", nullable=False),
            "validation_status": _col("varchar", nullable=False, length=32),
            "table_count": _col("integer", nullable=False),
            "column_count": _col("integer", nullable=False),
            "relation_count": _col("integer", nullable=False),
            "index_count": _col("integer", nullable=False),
            "category_count": _col("integer", nullable=False),
            "category_assignment_count": _col("integer", nullable=False),
            "managed_file_count": _col("integer", nullable=False),
            "manifest_json": _col("jsonb", nullable=False),
            "database_json": _col("jsonb", nullable=False),
            "tables_json": _col("jsonb", nullable=False),
            "columns_json": _col("jsonb", nullable=False),
            "relations_json": _col("jsonb", nullable=False),
            "indexes_json": _col("jsonb", nullable=False),
            "categories_json": _col("jsonb", nullable=False),
            "erd_json": _col("jsonb", nullable=False),
            "latest_run_json": _col("jsonb", nullable=False),
            "schema_snapshot_json": _col("jsonb", nullable=False),
            "preflight_json": _col("jsonb", nullable=False),
            "latest_diff_json": _col("jsonb", nullable=False),
            "managed_file_digests_json": _col("jsonb", nullable=False),
            "created_at": _col("timestamptz", nullable=False),
        },
        "uniques": {
            "uq_catalog_import_archive_sha256": ["archive_sha256"],
        },
        "indexes": {
            "ix_catalog_import_revisions_source_name": ["source_name"],
            "ix_catalog_import_revisions_package_readiness": ["package_readiness"],
            "ix_catalog_import_revisions_schema_fingerprint": ["schema_fingerprint"],
        },
        "fks": [],
    },
    "catalog_active_revisions": {
        "pk": ["id"],
        "columns": {
            "id": _col("integer", nullable=False),
            "source_name": _col("varchar", nullable=False, length=255),
            "catalog_import_revision_id": _col("integer", nullable=False),
            "activated_at": _col("timestamptz", nullable=False),
            "created_at": _col("timestamptz", nullable=False),
            "updated_at": _col("timestamptz", nullable=False),
        },
        "uniques": {
            "uq_catalog_active_source_name": ["source_name"],
        },
        "indexes": {
            "ix_catalog_active_revisions_source_name": ["source_name"],
            "ix_catalog_active_revisions_catalog_import_revision_id": [
                "catalog_import_revision_id"
            ],
        },
        "fks": [
            {
                "name": "catalog_active_revisions_catalog_import_revision_id_fkey",
                "columns": ["catalog_import_revision_id"],
                "referred_table": "catalog_import_revisions",
                "referred_columns": ["id"],
                "ondelete": "RESTRICT",
            }
        ],
    },
    "catalog_activation_events": {
        "pk": ["id"],
        "columns": {
            "id": _col("integer", nullable=False),
            "source_name": _col("varchar", nullable=False, length=255),
            "previous_revision_id": _col("integer", nullable=True),
            "activated_revision_id": _col("integer", nullable=False),
            "activated_at": _col("timestamptz", nullable=False),
        },
        "uniques": {},
        "indexes": {
            "ix_catalog_activation_events_source_name": ["source_name"],
            "ix_catalog_activation_events_previous_revision_id": [
                "previous_revision_id"
            ],
            "ix_catalog_activation_events_activated_revision_id": [
                "activated_revision_id"
            ],
            "ix_catalog_activation_events_activated_at": ["activated_at"],
        },
        "fks": [
            {
                "name": "catalog_activation_events_previous_revision_id_fkey",
                "columns": ["previous_revision_id"],
                "referred_table": "catalog_import_revisions",
                "referred_columns": ["id"],
                "ondelete": "RESTRICT",
            },
            {
                "name": "catalog_activation_events_activated_revision_id_fkey",
                "columns": ["activated_revision_id"],
                "referred_table": "catalog_import_revisions",
                "referred_columns": ["id"],
                "ondelete": "RESTRICT",
            },
        ],
    },
    "query_templates": {
        "pk": ["id"],
        "columns": {
            "id": _col("integer", nullable=False),
            "stable_key": _col("varchar", nullable=False, length=128),
            "name": _col("varchar", nullable=False, length=255),
            "description": _col("text", nullable=True),
            "source_name": _col("varchar", nullable=False, length=255),
            "target_schemas": _col("jsonb", nullable=False),
            "current_version_id": _col("integer", nullable=True),
            "enabled": _col("boolean", nullable=False),
            "created_at": _col("timestamptz", nullable=False),
            "updated_at": _col("timestamptz", nullable=False),
        },
        "uniques": {
            "uq_query_templates_source_stable_key": ["source_name", "stable_key"],
        },
        "indexes": {
            "ix_query_templates_source_name": ["source_name"],
            "ix_query_templates_current_version_id": ["current_version_id"],
        },
        "fks": [
            {
                "name": "fk_query_templates_current_version_id",
                "columns": ["current_version_id"],
                "referred_table": "query_template_versions",
                "referred_columns": ["id"],
                "ondelete": "RESTRICT",
            }
        ],
    },
    "query_template_versions": {
        "pk": ["id"],
        "columns": {
            "id": _col("integer", nullable=False),
            "template_id": _col("integer", nullable=False),
            "version": _col("integer", nullable=False),
            "sql_text": _col("text", nullable=False),
            "parameter_schema": _col("jsonb", nullable=False),
            "row_limit": _col("integer", nullable=False),
            "timeout_seconds": _col("integer", nullable=False),
            "compatibility_mode": _col("varchar", nullable=False, length=64),
            "catalog_revision_id": _col("integer", nullable=False),
            "catalog_fingerprint_constraint": _col(
                "varchar", nullable=False, length=255
            ),
            "approval_status": _col("varchar", nullable=False, length=32),
            "created_by": _col("varchar", nullable=True, length=255),
            "created_at": _col("timestamptz", nullable=False),
            "approved_by": _col("varchar", nullable=True, length=255),
            "approved_at": _col("timestamptz", nullable=True),
            "approval_note": _col("text", nullable=True),
        },
        "uniques": {
            "uq_query_template_versions_template_version": ["template_id", "version"],
        },
        "indexes": {
            "ix_query_template_versions_template_id": ["template_id"],
            "ix_query_template_versions_catalog_revision_id": ["catalog_revision_id"],
            "ix_query_template_versions_approval_status": ["approval_status"],
        },
        "fks": [
            {
                "name": "query_template_versions_template_id_fkey",
                "columns": ["template_id"],
                "referred_table": "query_templates",
                "referred_columns": ["id"],
                "ondelete": "CASCADE",
            },
            {
                "name": "query_template_versions_catalog_revision_id_fkey",
                "columns": ["catalog_revision_id"],
                "referred_table": "catalog_import_revisions",
                "referred_columns": ["id"],
                "ondelete": "RESTRICT",
            },
        ],
    },
    "query_template_review_events": {
        "pk": ["id"],
        "columns": {
            "id": _col("integer", nullable=False),
            "template_id": _col("integer", nullable=False),
            "version_id": _col("integer", nullable=False),
            "from_status": _col("varchar", nullable=False, length=32),
            "to_status": _col("varchar", nullable=False, length=32),
            "actor": _col("varchar", nullable=True, length=255),
            "note": _col("text", nullable=True),
            "created_at": _col("timestamptz", nullable=False),
        },
        "uniques": {},
        "indexes": {
            "ix_query_template_review_events_template_id": ["template_id"],
            "ix_query_template_review_events_version_id": ["version_id"],
            "ix_query_template_review_events_created_at": ["created_at"],
        },
        "fks": [
            {
                "name": "query_template_review_events_template_id_fkey",
                "columns": ["template_id"],
                "referred_table": "query_templates",
                "referred_columns": ["id"],
                "ondelete": "CASCADE",
            },
            {
                "name": "query_template_review_events_version_id_fkey",
                "columns": ["version_id"],
                "referred_table": "query_template_versions",
                "referred_columns": ["id"],
                "ondelete": "CASCADE",
            },
        ],
    },
}


class HistoricalSchemaIncompatibleError(RuntimeError):
    """Fail-closed adoption error. Message is sanitized (no DSN/host/data)."""


def _existing_tables() -> set[str]:
    bind = op.get_bind()
    return set(inspect(bind).get_table_names())


def _inspector(bind: Any | None = None):
    return inspect(bind if bind is not None else op.get_bind())


def _refuse(table: str, reason_code: str) -> None:
    # Sanitized operator-facing failure — no connection/column values/SQL payloads.
    raise HistoricalSchemaIncompatibleError(
        "historical schema adoption refused: "
        f"incompatible legacy table '{table}' ({reason_code})"
    )


def _type_family(sa_type: Any) -> tuple[str, int | None]:
    """Map inspector type to (family, optional varchar length)."""
    type_name = type(sa_type).__name__.casefold()
    as_str = str(sa_type).casefold()

    if "jsonb" in type_name or as_str.startswith("jsonb"):
        return "jsonb", None
    if "boolean" in type_name or as_str.startswith("boolean") or as_str == "bool":
        return "boolean", None
    if "integer" in type_name or as_str in {"integer", "int", "int4", "serial"}:
        return "integer", None
    if "text" in type_name or as_str == "text":
        return "text", None
    if "timestamp" in type_name or "timestamp" in as_str:
        # Require timezone-aware timestamps for DateTime(timezone=True).
        tz = bool(getattr(sa_type, "timezone", False)) or "with time zone" in as_str
        if not tz:
            return "timestamp", None
        return "timestamptz", None
    if "varchar" in type_name or "character varying" in as_str or as_str.startswith(
        "varchar"
    ):
        length = getattr(sa_type, "length", None)
        return "varchar", length
    if "string" in type_name:
        length = getattr(sa_type, "length", None)
        return "varchar", length
    return type_name, getattr(sa_type, "length", None)


def _collect_compat_issues(
    table: str, expected: _Schema, *, bind: Any | None = None
) -> list[str]:
    insp = _inspector(bind)
    issues: list[str] = []

    cols = {c["name"]: c for c in insp.get_columns(table)}
    expected_cols: Mapping[str, _Col] = expected["columns"]
    for name, spec in expected_cols.items():
        if name not in cols:
            issues.append(f"missing_column:{name}")
            continue
        actual = cols[name]
        if bool(actual.get("nullable")) != bool(spec["nullable"]):
            issues.append(f"nullability_mismatch:{name}")
        family, length = _type_family(actual["type"])
        if family != spec["family"]:
            issues.append(f"type_mismatch:{name}")
            continue
        expected_length = spec.get("length")
        if expected_length is not None and length is not None and length != expected_length:
            issues.append(f"type_length_mismatch:{name}")

    pk = insp.get_pk_constraint(table) or {}
    pk_cols = list(pk.get("constrained_columns") or [])
    if pk_cols != list(expected["pk"]):
        issues.append("pk_mismatch")

    uniques = {
        uq.get("name"): list(uq.get("column_names") or [])
        for uq in insp.get_unique_constraints(table)
        if uq.get("name")
    }
    # Unique constraints may also appear only as unique indexes.
    unique_indexes = {
        idx.get("name"): list(idx.get("column_names") or [])
        for idx in insp.get_indexes(table)
        if idx.get("unique") and idx.get("name")
    }
    for name, cols_expected in expected["uniques"].items():
        actual_cols = uniques.get(name) or unique_indexes.get(name)
        if actual_cols != cols_expected:
            issues.append(f"missing_unique:{name}")

    indexes = {
        idx.get("name"): list(idx.get("column_names") or [])
        for idx in insp.get_indexes(table)
        if idx.get("name") and not idx.get("unique")
    }
    for name, cols_expected in expected["indexes"].items():
        if indexes.get(name) != cols_expected:
            issues.append(f"missing_index:{name}")

    fks = insp.get_foreign_keys(table)
    fk_by_name = {fk.get("name"): fk for fk in fks if fk.get("name")}
    for expected_fk in expected["fks"]:
        name = expected_fk["name"]
        fk = fk_by_name.get(name)
        if fk is None:
            # Fall back to structural match (legacy renamed FKs still fail closed
            # unless columns/target/ondelete all match a present FK).
            structural = None
            for candidate in fks:
                if (
                    list(candidate.get("constrained_columns") or [])
                    == expected_fk["columns"]
                    and candidate.get("referred_table") == expected_fk["referred_table"]
                    and list(candidate.get("referred_columns") or [])
                    == expected_fk["referred_columns"]
                ):
                    structural = candidate
                    break
            if structural is None:
                issues.append(f"missing_fk:{name}")
                continue
            fk = structural
        if list(fk.get("constrained_columns") or []) != expected_fk["columns"]:
            issues.append(f"fk_columns_mismatch:{name}")
        if fk.get("referred_table") != expected_fk["referred_table"]:
            issues.append(f"fk_target_mismatch:{name}")
        if list(fk.get("referred_columns") or []) != expected_fk["referred_columns"]:
            issues.append(f"fk_ref_columns_mismatch:{name}")
        ondelete = (fk.get("options") or {}).get("ondelete")
        if (ondelete or "").upper() != expected_fk["ondelete"]:
            issues.append(f"fk_ondelete_mismatch:{name}")

    return issues


def assert_table_compatible(table: str, *, bind: Any | None = None) -> None:
    """Validate one adopted table against hist01 contract (migration or tests)."""
    if table not in _EXPECTED:
        _refuse(table, "unknown_adopted_table")
    issues = _collect_compat_issues(table, _EXPECTED[table], bind=bind)
    if issues:
        # Keep message bounded: first reason code only (no schema dumps).
        _refuse(table, issues[0])


def _assert_existing_adopted_tables_compatible(existing: set[str]) -> None:
    for table in _ADOPTED_TABLES:
        if table in existing:
            assert_table_compatible(table)


def upgrade() -> None:
    """Create missing adopted tables; adopt existing only when schema-compatible."""
    existing_at_start = _existing_tables()
    # Fail closed before creating anything when legacy tables are incompatible.
    _assert_existing_adopted_tables_compatible(existing_at_start)

    existing = set(existing_at_start)

    if "catalog_import_revisions" not in existing:
        _create_catalog_import_revisions()
        existing.add("catalog_import_revisions")

    if "catalog_active_revisions" not in existing:
        _create_catalog_active_revisions()
        existing.add("catalog_active_revisions")

    if "catalog_activation_events" not in existing:
        _create_catalog_activation_events()
        existing.add("catalog_activation_events")

    created_query_templates = "query_templates" not in existing
    if created_query_templates:
        # Circular FK added after query_template_versions exists (create path only).
        _create_query_templates_without_current_version_fk()
        existing.add("query_templates")

    if "query_template_versions" not in existing:
        _create_query_template_versions()
        existing.add("query_template_versions")

    if created_query_templates:
        op.create_foreign_key(
            "fk_query_templates_current_version_id",
            "query_templates",
            "query_template_versions",
            ["current_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    if "query_template_review_events" not in existing:
        _create_query_template_review_events()
        existing.add("query_template_review_events")

    # Final parity check for every adopted table now present.
    for table in _ADOPTED_TABLES:
        assert_table_compatible(table)


def _create_catalog_import_revisions() -> None:
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
            "manifest_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "database_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "tables_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "columns_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "relations_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "indexes_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "categories_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("erd_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "latest_run_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "schema_snapshot_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "preflight_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "latest_diff_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False
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
        sa.UniqueConstraint("archive_sha256", name="uq_catalog_import_archive_sha256"),
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


def _create_catalog_active_revisions() -> None:
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
        sa.UniqueConstraint("source_name", name="uq_catalog_active_source_name"),
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


def _create_catalog_activation_events() -> None:
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


def _create_query_templates_without_current_version_fk() -> None:
    op.create_table(
        "query_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stable_key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column(
            "target_schemas", postgresql.JSONB(astext_type=sa.Text()), nullable=False
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


def _create_query_template_versions() -> None:
    op.create_table(
        "query_template_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("sql_text", sa.Text(), nullable=False),
        sa.Column(
            "parameter_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("row_limit", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("compatibility_mode", sa.String(length=64), nullable=False),
        sa.Column("catalog_revision_id", sa.Integer(), nullable=False),
        sa.Column(
            "catalog_fingerprint_constraint", sa.String(length=255), nullable=False
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


def _create_query_template_review_events() -> None:
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
