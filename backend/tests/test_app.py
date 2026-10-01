"""Application smoke tests including production docs exposure."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import __version__
from app.main import create_app


def test_package_version_is_set() -> None:
    assert __version__
    assert isinstance(__version__, str)


def test_create_app_exposes_openapi_outside_production(
    test_settings_env: dict[str, str],
) -> None:
    """Development/test keep interactive docs (APP_ENV=test via fixture)."""
    application = create_app(init_db_on_startup=False)
    assert application.title
    assert application.docs_url == "/docs"
    assert application.redoc_url == "/redoc"
    assert application.openapi_url == "/openapi.json"
    openapi_paths = application.openapi()["paths"]
    assert "/health" in openapi_paths
    assert "/health/ready" in openapi_paths

    with TestClient(application) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.get("/docs").status_code == 200
        assert client.get("/redoc").status_code == 200


def test_production_disables_public_docs(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    from app.adapters.db.session import get_engine, get_session_factory
    from app.core.config import get_settings

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    application = create_app(init_db_on_startup=False)
    assert application.docs_url is None
    assert application.redoc_url is None
    assert application.openapi_url is None

    with TestClient(application) as client:
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        # Health remains available without docs.
        assert client.get("/health").status_code == 200

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
