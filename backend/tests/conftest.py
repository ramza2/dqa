"""Shared pytest fixtures for the DQA backend."""

import os

import pytest
from fastapi.testclient import TestClient

# Ensure deterministic settings before the application module is imported.
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_NAME", "DEMIS Query Assistant")
os.environ.setdefault("LOG_LEVEL", "INFO")
os.environ.setdefault("DQA_DB_HOST", "localhost")
os.environ.setdefault("DQA_DB_PORT", "5432")
os.environ.setdefault("DQA_DB_NAME", "dqa")
os.environ.setdefault("DQA_DB_USER", "dqa")
os.environ.setdefault("DQA_DB_PASSWORD", "dqa")


@pytest.fixture()
def client() -> TestClient:
    """HTTP client bound to the FastAPI app."""
    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
    get_settings.cache_clear()
