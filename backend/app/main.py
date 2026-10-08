"""FastAPI application entrypoint for DEMIS Query Assistant."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from app import __version__
from app.adapters.db.migration_head import assert_migrations_at_head
from app.api.routes import api_router
from app.core.config import Settings, get_settings
from app.mcp.server import (
    build_protected_mcp_asgi,
    mcp_session_lifespan,
    mount_mcp_asgi,
)


def create_app(*, check_migrations_on_startup: bool = True) -> FastAPI:
    """Build and configure the FastAPI application.

    By default, lifespan performs a read-only Alembic head check and refuses to
    start when the database is not at the current script head. Schema creation
    is never performed at startup; operators must run ``alembic upgrade head``
    (for example via ``./scripts/dqa-migrate.sh``) before bringing the backend up.
    """
    settings = get_settings()
    mcp: FastMCP | None = None
    # May be None when disabled, or when private-boundary declaration is not
    # loopback (fail closed — DQA_MCP_BIND_HOST does not control Uvicorn listen).
    mcp_bundle = build_protected_mcp_asgi(settings)
    if mcp_bundle is not None:
        mcp = mcp_bundle[0]

    lifespan = _build_lifespan(
        check_migrations_on_startup=check_migrations_on_startup,
        mcp=mcp,
    )
    docs_urls = _docs_urls_for_env(settings)
    application = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "DEMIS Query Assistant backend. "
            "Provides Catalog Package validation/import/activation, Catalog metadata "
            "query APIs, Data Discovery schema search (keyword/semantic/hybrid), "
            "approved Query Template management, LLM-assisted template "
            "recommendation and parameter extraction, deterministic execution "
            "preview, audited read-only DEMIS query execution, optional internal "
            "MCP Streamable HTTP with Discovery and Template Query tools "
            "(Phase 28-C), and operational health/readiness endpoints."
        ),
        lifespan=lifespan,
        docs_url=docs_urls["docs_url"],
        redoc_url=docs_urls["redoc_url"],
        openapi_url=docs_urls["openapi_url"],
    )
    application.include_router(api_router)
    if mcp_bundle is not None:
        mcp_obj, registry, asgi_app, mount_path = mcp_bundle
        mount_mcp_asgi(
            application,
            mcp=mcp_obj,
            registry=registry,
            asgi_app=asgi_app,
            mount_path=mount_path,
        )
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


def _build_lifespan(*, check_migrations_on_startup: bool, mcp: FastMCP | None):
    @asynccontextmanager
    async def _lifespan(_application: FastAPI):
        if check_migrations_on_startup:
            assert_migrations_at_head()
        async with mcp_session_lifespan(mcp):
            yield

    return _lifespan


app = create_app()
