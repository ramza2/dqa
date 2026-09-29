"""API route modules."""

from fastapi import APIRouter

from app.api.routes import (
    audit_events,
    auth,
    catalog_active,
    catalog_imports,
    catalog_packages,
    catalog_query,
    connection_profiles,
    health,
    parameter_extraction,
    query_executions,
    query_templates,
    recommendations,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(catalog_packages.router)
api_router.include_router(catalog_imports.router)
# Register query routes before the bare /{source_name} summary route pattern group.
api_router.include_router(catalog_query.query_router)
api_router.include_router(catalog_active.active_router)
api_router.include_router(catalog_active.activations_router)
api_router.include_router(query_templates.router)
api_router.include_router(recommendations.router)
api_router.include_router(parameter_extraction.router)
api_router.include_router(query_executions.router)
api_router.include_router(connection_profiles.router)
api_router.include_router(audit_events.router)
