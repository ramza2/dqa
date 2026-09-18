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
            "This skeleton provides settings, DQA PostgreSQL connectivity, "
            "and health endpoints only."
        ),
    )
    application.include_router(api_router)
    return application


app = create_app()
