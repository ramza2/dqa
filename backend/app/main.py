"""FastAPI application entrypoint for DEMIS Query Assistant."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.adapters.db.deps import init_db_schema
from app.api.routes import api_router
from app.core.config import Settings, get_settings


def create_app(*, init_db_on_startup: bool = True) -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    lifespan = _db_lifespan if init_db_on_startup else None
    docs_urls = _docs_urls_for_env(settings)
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "DEMIS Query Assistant backend. "
            "Provides Catalog Package validation/import/activation, Catalog metadata "
            "query APIs, approved Query Template management, LLM-assisted template "
            "recommendation and parameter extraction, deterministic execution "
            "preview, audited read-only DEMIS query execution, and operational "
            "health/readiness endpoints."
        ),
        lifespan=lifespan,
        docs_url=docs_urls["docs_url"],
        redoc_url=docs_urls["redoc_url"],
        openapi_url=docs_urls["openapi_url"],
    )
    application.include_router(api_router)
    return application


def _docs_urls_for_env(settings: Settings) -> dict[str, str | None]:
    """Disable public OpenAPI/docs surfaces in production (attack-surface reduction).

    This is not an authentication control. Development/test keep interactive docs.
    """
    if settings.app_env == "production":
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
    }


@asynccontextmanager
async def _db_lifespan(_application: FastAPI):
    """Initialize application schema on startup.

    Alembic (`alembic upgrade head`) is the preferred path for migration-owned
    tables. ``create_all`` remains for historical catalog/template bootstrap
    until full migration ownership covers those tables. Prefer migrate-then-start
    on fresh databases (see docs/runtime-and-deployment.md).
    """
    init_db_schema()
    yield


app = create_app()
