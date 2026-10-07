"""Focused regression tests for Alembic historical schema adoption (Phase 24-A)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from alembic.util.exc import CommandError
from sqlalchemy import inspect, text

from app.core.config import get_settings

_ADOPTED = (
    "catalog_import_revisions",
    "catalog_active_revisions",
    "catalog_activation_events",
    "query_templates",
    "query_template_versions",
    "query_template_review_events",
)

_ALL_OWNED = _ADOPTED + (
    "connection_profiles",
    "query_audit_events",
)

_HEAD = "20261007_hist01"
_PREV = "20260929_audit01"


def _drop_dqa_tables(engine) -> None:
    tables = (
        "query_template_review_events",
        "query_template_versions",
        "query_templates",
        "catalog_activation_events",
        "catalog_active_revisions",
        "catalog_import_revisions",
        "query_audit_events",
        "connection_profiles",
        "alembic_version",
    )
    with engine.begin() as conn:
        for name in tables:
            conn.execute(text(f"DROP TABLE IF EXISTS {name} CASCADE"))


def _alembic_upgrade(revision: str = "head") -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    command.upgrade(cfg, revision)


def _current_revision(engine) -> str | None:
    with engine.begin() as conn:
        if not inspect(engine).has_table("alembic_version"):
            return None
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _type_family(sa_type) -> tuple[str, int | None]:
    """Mirror hist01 coarse type families for ORM/DB parity checks."""
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
    # ORM DateTime(...) and PG TIMESTAMP WITH TIME ZONE both map here.
    if (
        "timestamp" in type_name
        or "timestamp" in as_str
        or type_name == "datetime"
        or as_str.startswith("datetime")
    ):
        tz = bool(getattr(sa_type, "timezone", False)) or "with time zone" in as_str
        if not tz:
            return "timestamp", None
        return "timestamptz", None
    if "varchar" in type_name or "character varying" in as_str or as_str.startswith(
        "varchar"
    ):
        return "varchar", getattr(sa_type, "length", None)
    if "string" in type_name:
        return "varchar", getattr(sa_type, "length", None)
    return type_name, getattr(sa_type, "length", None)


def test_alembic_chain_hist01_follows_audit01() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    rev = script.get_revision(_HEAD)
    assert rev is not None
    assert rev.down_revision == _PREV
    heads = script.get_heads()
    assert list(heads) == [_HEAD]


def test_fresh_db_upgrade_head_creates_full_schema(
    test_settings_env: dict[str, str],
) -> None:
    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    _drop_dqa_tables(engine)

    _alembic_upgrade("head")

    insp = inspect(engine)
    for name in _ALL_OWNED:
        assert insp.has_table(name), name
    assert _current_revision(engine) == _HEAD

    # Spot-check circular FK and unique names match ORM/create_all conventions.
    template_fks = {fk["name"] for fk in insp.get_foreign_keys("query_templates")}
    assert "fk_query_templates_current_version_id" in template_fks
    import_uqs = {
        uq["name"] for uq in insp.get_unique_constraints("catalog_import_revisions")
    }
    assert "uq_catalog_import_archive_sha256" in import_uqs


def test_legacy_create_all_adoption_preserves_rows(
    test_settings_env: dict[str, str],
) -> None:
    """Simulate create_all-era DB at audit01, then adopt via hist01 without data loss."""
    from app.adapters.db.session import get_engine, get_session_factory
    from app.models import Base

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    _drop_dqa_tables(engine)

    # Baseline Alembic-owned tables only (pre-adoption head).
    _alembic_upgrade(_PREV)
    assert _current_revision(engine) == _PREV
    assert inspect(engine).has_table("connection_profiles")
    assert inspect(engine).has_table("query_audit_events")
    for name in _ADOPTED:
        assert not inspect(engine).has_table(name), name

    # Historical fixture only: simulate pre-24-B create_all-era tables in-test.
    # Production runtime no longer exposes init_db_schema / create_all.
    Base.metadata.create_all(bind=engine)
    for name in _ADOPTED:
        assert inspect(engine).has_table(name), name

    marker_source = "legacy-adoption-marker"
    marker_sha = "a" * 64
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO catalog_import_revisions (
                    source_name, db_type, package_format, package_version,
                    package_readiness, schema_fingerprint, archive_sha256,
                    manifest_sha256, generated_at, validation_status,
                    table_count, column_count, relation_count, index_count,
                    category_count, category_assignment_count, managed_file_count,
                    manifest_json, database_json, tables_json, columns_json,
                    relations_json, indexes_json, categories_json, erd_json,
                    latest_run_json, schema_snapshot_json, preflight_json,
                    latest_diff_json, managed_file_digests_json
                ) VALUES (
                    :source_name, 'oracle', 'demis-catalog-package', '2.0',
                    'READY', 'fp-legacy', :archive_sha256,
                    :manifest_sha256, :generated_at, 'VALID',
                    0, 0, 0, 0,
                    0, 0, 0,
                    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                    '{}'::jsonb, '{}'::jsonb
                )
                """
            ),
            {
                "source_name": marker_source,
                "archive_sha256": marker_sha,
                "manifest_sha256": "b" * 64,
                "generated_at": datetime.now(UTC),
            },
        )
        before_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM catalog_import_revisions "
                "WHERE source_name = :source_name"
            ),
            {"source_name": marker_source},
        ).scalar()
    assert before_count == 1

    # Adoption upgrade must not recreate/drop existing historical tables.
    _alembic_upgrade("head")
    assert _current_revision(engine) == _HEAD

    with engine.begin() as conn:
        after_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM catalog_import_revisions "
                "WHERE source_name = :source_name AND archive_sha256 = :sha"
            ),
            {"source_name": marker_source, "sha": marker_sha},
        ).scalar()
        total = conn.execute(text("SELECT COUNT(*) FROM catalog_import_revisions")).scalar()
    assert after_count == 1
    assert total == 1

    for name in _ALL_OWNED:
        assert inspect(engine).has_table(name), name


def test_incompatible_legacy_schema_refuses_hist01_adoption(
    test_settings_env: dict[str, str],
) -> None:
    """Stale/legacy table that only shares a name must fail closed (no hist01 stamp)."""
    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    _drop_dqa_tables(engine)

    _alembic_upgrade(_PREV)
    assert _current_revision(engine) == _PREV

    # Deliberately incompatible fixture: same table name, missing required columns /
    # uniques / indexes / JSONB payload columns that current ORM + hist01 require.
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE catalog_import_revisions (
                    id SERIAL PRIMARY KEY,
                    source_name VARCHAR(255) NOT NULL,
                    legacy_only_flag BOOLEAN NOT NULL DEFAULT TRUE
                )
                """
            )
        )

    assert inspect(engine).has_table("catalog_import_revisions")
    # Other adopted tables absent — upgrade must refuse before create/stamp.
    for name in _ADOPTED:
        if name == "catalog_import_revisions":
            continue
        assert not inspect(engine).has_table(name), name

    with pytest.raises((CommandError, RuntimeError)) as exc_info:
        _alembic_upgrade("head")

    message = str(exc_info.value)
    assert "historical schema adoption refused" in message
    assert "catalog_import_revisions" in message
    # Sanitized: no DSN / host / credential leakage in operator message.
    assert "password" not in message.casefold()
    assert "@" not in message
    assert "postgresql://" not in message.casefold()

    # Fail closed: revision must remain at audit01; hist01 must not be stamped.
    assert _current_revision(engine) == _PREV

    # No repair/create of sibling adopted tables after refusal.
    for name in _ADOPTED:
        if name == "catalog_import_revisions":
            continue
        assert not inspect(engine).has_table(name), name

    # Incompatible stub retained as-is (no drop/recreate).
    stub_cols = {
        c["name"] for c in inspect(engine).get_columns("catalog_import_revisions")
    }
    assert stub_cols == {"id", "source_name", "legacy_only_flag"}


def test_fresh_hist01_schema_matches_orm_metadata_parity(
    test_settings_env: dict[str, str],
) -> None:
    """Fresh alembic head must satisfy hist01 contract and match ORM core schema."""
    import importlib.util
    from pathlib import Path

    from sqlalchemy import UniqueConstraint

    from app.adapters.db.session import get_engine, get_session_factory
    from app.models import Base

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20261007_hist01_adopt_historical_schema.py"
    )
    spec = importlib.util.spec_from_file_location(
        "hist01_adoption_migration", migration_path
    )
    assert spec is not None and spec.loader is not None
    hist01 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hist01)

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    _drop_dqa_tables(engine)
    _alembic_upgrade("head")
    assert _current_revision(engine) == _HEAD

    insp = inspect(engine)
    for table_name in _ADOPTED:
        hist01.assert_table_compatible(table_name, bind=engine)

        orm_table = Base.metadata.tables[table_name]
        db_cols = {c["name"]: c for c in insp.get_columns(table_name)}

        for col in orm_table.columns:
            assert col.name in db_cols, f"{table_name}.{col.name} missing in DB"
            actual = db_cols[col.name]
            assert bool(actual.get("nullable")) == bool(col.nullable), (
                f"{table_name}.{col.name} nullability"
            )
            expected_family, expected_len = _type_family(col.type)
            actual_family, actual_len = _type_family(actual["type"])
            assert actual_family == expected_family, (
                f"{table_name}.{col.name} type family"
            )
            if expected_len is not None and actual_len is not None:
                assert actual_len == expected_len, (
                    f"{table_name}.{col.name} type length"
                )

        pk = insp.get_pk_constraint(table_name) or {}
        assert list(pk.get("constrained_columns") or []) == list(
            orm_table.primary_key.columns.keys()
        )

        db_uq_names = {
            uq.get("name")
            for uq in insp.get_unique_constraints(table_name)
            if uq.get("name")
        }
        db_uq_names |= {
            idx.get("name")
            for idx in insp.get_indexes(table_name)
            if idx.get("unique") and idx.get("name")
        }
        for uq in orm_table.constraints:
            if isinstance(uq, UniqueConstraint) and uq.name:
                assert uq.name in db_uq_names, f"{table_name} missing unique {uq.name}"

        assert set(hist01._EXPECTED[table_name]["indexes"]) <= {
            idx.get("name")
            for idx in insp.get_indexes(table_name)
            if idx.get("name") and not idx.get("unique")
        }


def test_hist01_downgrade_is_non_destructive(
    test_settings_env: dict[str, str],
) -> None:
    from alembic import command
    from alembic.config import Config

    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    engine = get_engine()
    _drop_dqa_tables(engine)
    _alembic_upgrade("head")

    marker_source = "downgrade-keep-marker"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO catalog_import_revisions (
                    source_name, db_type, package_format, package_version,
                    package_readiness, schema_fingerprint, archive_sha256,
                    manifest_sha256, generated_at, validation_status,
                    table_count, column_count, relation_count, index_count,
                    category_count, category_assignment_count, managed_file_count,
                    manifest_json, database_json, tables_json, columns_json,
                    relations_json, indexes_json, categories_json, erd_json,
                    latest_run_json, schema_snapshot_json, preflight_json,
                    latest_diff_json, managed_file_digests_json
                ) VALUES (
                    :source_name, 'oracle', 'demis-catalog-package', '2.0',
                    'READY', 'fp-down', :archive_sha256,
                    :manifest_sha256, :generated_at, 'VALID',
                    0, 0, 0, 0,
                    0, 0, 0,
                    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                    '{}'::jsonb, '{}'::jsonb, '{}'::jsonb,
                    '{}'::jsonb, '{}'::jsonb
                )
                """
            ),
            {
                "source_name": marker_source,
                "archive_sha256": "c" * 64,
                "manifest_sha256": "d" * 64,
                "generated_at": datetime.now(UTC),
            },
        )

    cfg = Config("alembic.ini")
    command.downgrade(cfg, _PREV)
    assert _current_revision(engine) == _PREV

    # Tables and rows must remain after non-destructive downgrade.
    for name in _ADOPTED:
        assert inspect(engine).has_table(name), name
    with engine.begin() as conn:
        kept = conn.execute(
            text(
                "SELECT COUNT(*) FROM catalog_import_revisions "
                "WHERE source_name = :source_name"
            ),
            {"source_name": marker_source},
        ).scalar()
    assert kept == 1
