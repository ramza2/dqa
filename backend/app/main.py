"""FastAPI application entrypoint for DEMIS Query Assistant."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.adapters.db.deps import init_db_schema
from app.api.routes import api_router
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_application: FastAPI):
    """Initialize application schema on startup (no Alembic yet)."""
    init_db_schema()
    yield


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "DEMIS Query Assistant backend. "
            "Provides settings, DQA PostgreSQL connectivity, health endpoints, "
            "Catalog Package v2 validation, and immutable catalog import persistence."
        ),
        lifespan=lifespan,
    )
    application.include_router(api_router)
    return application


app = create_app()
