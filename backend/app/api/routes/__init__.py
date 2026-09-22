"""API route modules."""

from fastapi import APIRouter

from app.api.routes import (
    catalog_active,
    catalog_imports,
    catalog_packages,
    catalog_query,
    health,
    query_templates,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(catalog_packages.router)
api_router.include_router(catalog_imports.router)
# Register query routes before the bare /{source_name} summary route pattern group.
api_router.include_router(catalog_query.query_router)
api_router.include_router(catalog_active.active_router)
api_router.include_router(catalog_active.activations_router)
api_router.include_router(query_templates.router)
