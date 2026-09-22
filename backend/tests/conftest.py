"""Shared pytest fixtures for the DQA backend."""

import pytest
from fastapi.testclient import TestClient

# Deterministic defaults applied via monkeypatch in fixtures (not setdefault).
# Password matches local Cloud Agent PostgreSQL (scripts/cloud-agent-start.sh).
_TEST_ENV = {
    "APP_ENV": "test",
    "APP_NAME": "DEMIS Query Assistant",
    "LOG_LEVEL": "INFO",
    "DQA_DB_HOST": "localhost",
    "DQA_DB_PORT": "5432",
    "DQA_DB_NAME": "dqa",
    "DQA_DB_USER": "dqa",
    "DQA_DB_PASSWORD": "dqa",
}


def _clear_db_caches() -> None:
    from app.adapters.db.session import get_engine, get_session_factory
    from app.core.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture()
def test_settings_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Force a known settings environment for the duration of a test."""
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(_TEST_ENV)


@pytest.fixture()
def client(test_settings_env: dict[str, str]) -> TestClient:
    """HTTP client for validation/health tests (no DB schema bootstrap)."""
    from app.main import create_app

    _clear_db_caches()
    application = create_app(init_db_on_startup=False)
    with TestClient(application) as test_client:
        yield test_client
    _clear_db_caches()


@pytest.fixture()
def db_client(test_settings_env: dict[str, str]) -> TestClient:
    """HTTP client for import/history integration tests (bootstraps DB schema)."""
    from app.main import create_app

    _clear_db_caches()
    application = create_app(init_db_on_startup=True)
    with TestClient(application) as test_client:
        yield test_client
    _clear_db_caches()


@pytest.fixture()
def db_session(test_settings_env: dict[str, str]):
    """Transactional DB session with clean catalog_import_revisions table."""
    from sqlalchemy import inspect, text

    from app.adapters.db.deps import init_db_schema
    from app.adapters.db.session import get_engine, get_session_factory

    _clear_db_caches()
    init_db_schema()
    engine = get_engine()
    # Ensure clean catalog tables for persistence tests without dropping unrelated objects.
    tables = (
        "query_template_review_events",
        "query_template_versions",
        "query_templates",
        "catalog_activation_events",
        "catalog_active_revisions",
        "catalog_import_revisions",
    )
    existing = [name for name in tables if inspect(engine).has_table(name)]
    if existing:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE TABLE "
                    + ", ".join(existing)
                    + " RESTART IDENTITY CASCADE"
                )
            )

    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        _clear_db_caches()
