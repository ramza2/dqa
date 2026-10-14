"""Explicit administrator-only metadata inspection (no automatic Catalog import)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.public_errors import PublicErrorSpec, build_public_http_error
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.core.config import Settings, get_settings
from app.schemas.schema_inspector import SchemaInspectionRequest, SchemaInspectionSummary
from app.services.schema_inspection import SchemaInspectionError, inspect_configured_schema

router = APIRouter(prefix="/api/v1/schema-inspector", tags=["schema-inspector"])

_PUBLIC_ERRORS = {
    "INSPECTOR_DISABLED": PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "schema inspection is disabled",
    ),
    "INSPECTOR_ENV_NOT_ALLOWED": PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "schema inspection is not approved for this environment",
    ),
    "INSPECTOR_NOT_CONFIGURED": PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "schema inspection target is not configured",
    ),
    "INSPECTOR_METADATA_FAILED": PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "schema metadata collection failed",
    ),
}


@router.post("/inspect", response_model=SchemaInspectionSummary)
def inspect_schema(
    _body: SchemaInspectionRequest,
    settings: Settings = Depends(get_settings),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> SchemaInspectionSummary:
    """Inspect one server-configured schema only; do not persist or activate."""
    try:
        return inspect_configured_schema(settings)
    except SchemaInspectionError as exc:
        raise build_public_http_error(
            error_code=exc.code,
            contracts=_PUBLIC_ERRORS,
            fallback_code="INSPECTOR_INTERNAL_ERROR",
            fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            fallback_message="schema inspection failed",
        ) from None
    except Exception:
        # Ensure any unreviewed driver/programming failure never reaches a client.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "INSPECTOR_INTERNAL_ERROR",
                "message": "schema inspection failed",
            },
        ) from None
