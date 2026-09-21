"""FastAPI application entrypoint for DEMIS Query Assistant."""

from fastapi import FastAPI

from app import __version__
from app.api.routes import api_router
from app.core.config import get_settings


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "DEMIS Query Assistant backend. "
            "Provides settings, DQA PostgreSQL connectivity, health endpoints, "
            "and Catalog Package v2 validation (no import persistence yet)."
        ),
    )
    application.include_router(api_router)
    return application


app = create_app()
