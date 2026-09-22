"""API route modules."""

from fastapi import APIRouter

from app.api.routes import catalog_active, catalog_imports, catalog_packages, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(catalog_packages.router)
api_router.include_router(catalog_imports.router)
api_router.include_router(catalog_active.active_router)
api_router.include_router(catalog_active.activations_router)
