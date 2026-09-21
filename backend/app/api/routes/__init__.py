"""API route modules."""

from fastapi import APIRouter

from app.api.routes import catalog_packages, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(catalog_packages.router)
