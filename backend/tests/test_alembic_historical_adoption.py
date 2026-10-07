"""Focused regression tests for Alembic historical schema adoption (Phase 24-A)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
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
    from app.adapters.db.deps import init_db_schema
    from app.adapters.db.session import get_engine, get_session_factory

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

    # Legacy bootstrap path still used by runtime create_all.
    init_db_schema()
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
