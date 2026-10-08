"""Phase 24-B: Alembic-only schema lifecycle and startup migration-head checks."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.core.config import get_settings

_HEAD = "20261008_dd02"
_PREV = "20261008_dd01"

_DQA_TABLES = (
    "query_template_review_events",
    "query_template_versions",
    "query_templates",
    "data_discovery_embeddings",
    "data_discovery_documents",
    "catalog_activation_events",
    "catalog_active_revisions",
    "catalog_import_revisions",
    "query_audit_events",
    "connection_profiles",
    "alembic_version",
)


def _clear_caches() -> None:
    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def _drop_dqa_tables(engine) -> None:
    with engine.begin() as conn:
        for name in _DQA_TABLES:
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


def test_runtime_modules_do_not_call_create_all() -> None:
    """Static regression: production app/adapters must not invoke create_all."""
    from pathlib import Path

    roots = [
        Path(__file__).resolve().parents[1] / "app",
        Path(__file__).resolve().parents[1] / "alembic" / "check_at_head.py",
    ]
    offenders: list[str] = []
    for root in roots:
        paths = [root] if root.is_file() else root.rglob("*.py")
        for path in paths:
            text_src = path.read_text(encoding="utf-8")
            if "create_all" in text_src:
                offenders.append(str(path.relative_to(Path(__file__).resolve().parents[1])))
    assert offenders == []


def test_init_db_schema_helper_removed() -> None:
    import app.adapters.db.deps as deps

    assert not hasattr(deps, "init_db_schema")


def test_fresh_db_startup_does_not_create_tables(
    test_settings_env: dict[str, str],
) -> None:
    from app.adapters.db.session import get_engine
    from app.main import create_app
    from app.models import Base

    _clear_caches()
    engine = get_engine()
    _drop_dqa_tables(engine)

    original_create_all = Base.metadata.create_all
    create_all = MagicMock(wraps=original_create_all)
    Base.metadata.create_all = create_all  # type: ignore[method-assign]
    try:
        application = create_app(check_migrations_on_startup=True)
        with pytest.raises(Exception) as exc_info:
            with TestClient(application):
                pass
        message = str(exc_info.value)
        assert "migration check failed" in message
        assert "password" not in message.casefold()
        assert "postgresql://" not in message.casefold()

        insp = inspect(engine)
        for name in _DQA_TABLES:
            if name == "alembic_version":
                continue
            assert not insp.has_table(name), name
        create_all.assert_not_called()
    finally:
        Base.metadata.create_all = original_create_all  # type: ignore[method-assign]
        _clear_caches()


def test_unmigrated_startup_fails_closed(
    test_settings_env: dict[str, str],
) -> None:
    from app.adapters.db.migration_head import MigrationHeadError
    from app.adapters.db.session import get_engine
    from app.main import create_app

    _clear_caches()
    engine = get_engine()
    _drop_dqa_tables(engine)
    _alembic_upgrade(_PREV)
    assert _current_revision(engine) == _PREV

    application = create_app(check_migrations_on_startup=True)
    with pytest.raises((MigrationHeadError, Exception)) as exc_info:
        with TestClient(application):
            pass
    message = str(exc_info.value)
    assert "migration check failed" in message
    assert _HEAD in message or "not at Alembic head" in message
    assert _current_revision(engine) == _PREV


def test_migrated_startup_succeeds(
    test_settings_env: dict[str, str],
) -> None:
    from app.adapters.db.session import get_engine
    from app.main import create_app
    from app.models import Base

    _clear_caches()
    engine = get_engine()
    _drop_dqa_tables(engine)
    _alembic_upgrade("head")
    assert _current_revision(engine) == _HEAD

    create_all = MagicMock()
    original = Base.metadata.create_all
    Base.metadata.create_all = create_all  # type: ignore[method-assign]
    try:
        application = create_app(check_migrations_on_startup=True)
        with TestClient(application) as client:
            response = client.get("/health")
            assert response.status_code == 200
        create_all.assert_not_called()
    finally:
        Base.metadata.create_all = original  # type: ignore[method-assign]
        _clear_caches()


def test_migration_head_checker_is_non_mutating(
    test_settings_env: dict[str, str],
) -> None:
    from app.adapters.db.migration_head import assert_migrations_at_head, inspect_migration_head
    from app.adapters.db.session import get_engine

    _clear_caches()
    engine = get_engine()
    _drop_dqa_tables(engine)
    _alembic_upgrade("head")

    before_tables = set(inspect(engine).get_table_names())
    before_rev = _current_revision(engine)
    with engine.begin() as conn:
        before_count = conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar()

    status = inspect_migration_head(engine=engine)
    assert status.ok
    assert_migrations_at_head(engine=engine)

    after_tables = set(inspect(engine).get_table_names())
    after_rev = _current_revision(engine)
    with engine.begin() as conn:
        after_count = conn.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar()

    assert after_tables == before_tables
    assert after_rev == before_rev == _HEAD
    assert after_count == before_count == 1


def test_engine_creation_failure_sanitizes_secret_marker(
    monkeypatch: pytest.MonkeyPatch,
    test_settings_env: dict[str, str],
) -> None:
    """Engine/settings failures must not leak DSN/password markers publicly."""
    from app.adapters.db.migration_head import (
        MigrationHeadError,
        assert_migrations_at_head,
        inspect_migration_head,
        status_message,
    )

    secret_marker = (
        "SUPER_SECRET_DSN_MARKER_postgresql://dqa:hunter2@evil-host.example:5432/dqa"
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError(f"create_engine failed with {secret_marker}")

    monkeypatch.setattr("sqlalchemy.create_engine", _boom)
    _clear_caches()

    status = inspect_migration_head()  # self-managed engine path
    assert status.ok is False
    assert status.reason_code == "database_error"
    assert status.detail == "database/Alembic error (RuntimeError)"
    public = status_message(status)
    assert secret_marker not in status.detail
    assert secret_marker not in public
    assert "hunter2" not in public
    assert "evil-host" not in public
    assert "postgresql://" not in public.casefold()

    with pytest.raises(MigrationHeadError) as exc_info:
        assert_migrations_at_head()
    raised = str(exc_info.value)
    assert secret_marker not in raised
    assert "hunter2" not in raised
    assert "evil-host" not in raised
    assert "postgresql://" not in raised.casefold()
    assert "database/Alembic error (RuntimeError)" in raised


def test_cli_check_at_head_reuses_application_checker(
    test_settings_env: dict[str, str],
) -> None:
    import importlib.util
    from pathlib import Path

    from app.adapters.db.session import get_engine

    path = (
        Path(__file__).resolve().parents[1] / "alembic" / "check_at_head.py"
    )
    spec = importlib.util.spec_from_file_location("dqa_check_at_head", path)
    assert spec is not None and spec.loader is not None
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    _clear_caches()
    engine = get_engine()
    _drop_dqa_tables(engine)

    assert cli.main() == 1

    _alembic_upgrade("head")
    assert cli.main() == 0
