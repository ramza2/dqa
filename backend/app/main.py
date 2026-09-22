"""FastAPI application entrypoint for DEMIS Query Assistant."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.adapters.db.deps import init_db_schema
from app.api.routes import api_router
from app.core.config import get_settings


def create_app(*, init_db_on_startup: bool = True) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    lifespan = _db_lifespan if init_db_on_startup else None
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "DEMIS Query Assistant backend. "
            "Provides settings, DQA PostgreSQL connectivity, health endpoints, "
            "Catalog Package v2 validation, immutable catalog import persistence, "
            "Active Catalog management, Active Catalog metadata query APIs, "
            "and draft Query Template registry (no execution)."
        ),
        lifespan=lifespan,
    )
    application.include_router(api_router)
    return application


@asynccontextmanager
async def _db_lifespan(_application: FastAPI):
    """Initialize application schema on startup (no Alembic yet)."""
    init_db_schema()
    yield


app = create_app()
