"""Baseline smoke tests for the application package."""

from app import __version__
from app.main import create_app


def test_package_version_is_set() -> None:
    assert __version__
    assert isinstance(__version__, str)


def test_create_app_exposes_openapi() -> None:
    application = create_app()
    assert application.title
    openapi_paths = application.openapi()["paths"]
    assert "/health" in openapi_paths
    assert "/health/ready" in openapi_paths
