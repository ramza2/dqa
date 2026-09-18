"""Shared pytest fixtures for the DQA backend."""

import pytest
from fastapi.testclient import TestClient

# Deterministic defaults applied via monkeypatch in fixtures (not setdefault).
_TEST_ENV = {
    "APP_ENV": "test",
    "APP_NAME": "DEMIS Query Assistant",
    "LOG_LEVEL": "INFO",
    "DQA_DB_HOST": "localhost",
    "DQA_DB_PORT": "5432",
    "DQA_DB_NAME": "dqa",
    "DQA_DB_USER": "dqa",
    "DQA_DB_PASSWORD": "test-password",
}


@pytest.fixture()
def test_settings_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Force a known settings environment for the duration of a test."""
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)
    return dict(_TEST_ENV)


@pytest.fixture()
def client(test_settings_env: dict[str, str]) -> TestClient:
    """HTTP client bound to the FastAPI app with deterministic settings."""
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
    get_settings.cache_clear()
