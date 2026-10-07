"""Active Catalog and activation-history query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import (
    CatalogActivationError,
    CatalogActivationErrorCode,
)
from app.adapters.db.deps import get_db_session
from app.api.public_errors import PublicErrorSpec, build_public_http_error
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.catalog_package import (
    CatalogActivationEventSummary,
    CatalogActiveSummary,
)
from app.services.catalog_active import (
    get_active_catalog,
    list_activation_events,
    list_active_catalogs,
)

active_router = APIRouter(prefix="/api/v1/catalog/active", tags=["catalog-active"])
activations_router = APIRouter(prefix="/api/v1/catalog/activations", tags=["catalog-activations"])

_ACTIVATION_PUBLIC_ERRORS = {
    CatalogActivationErrorCode.IMPORT_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "catalog import revision not found",
    ),
    CatalogActivationErrorCode.ACTIVE_REVISION_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "active catalog revision not found",
    ),
    CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "catalog revision is not activatable",
    ),
}


@active_router.get("", response_model=list[CatalogActiveSummary])
def list_active(
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> list[CatalogActiveSummary]:
    """List current active Catalog pointers (one per source)."""
    return [
        CatalogActiveSummary(
            source_name=view.source_name,
            revision_id=view.revision_id,
            schema_fingerprint=view.schema_fingerprint,
            package_version=view.package_version,
            package_readiness=view.package_readiness,  # type: ignore[arg-type]
            activated_at=view.activated_at,
        )
        for view in list_active_catalogs(session)
    ]


@active_router.get("/{source_name}", response_model=CatalogActiveSummary)
def get_active(
    source_name: str,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> CatalogActiveSummary:
    """Return the active Catalog pointer for one source_name."""
    try:
        view = get_active_catalog(session, source_name)
    except CatalogActivationError as exc:
        raise activation_http_error(exc) from exc
    return CatalogActiveSummary(
        source_name=view.source_name,
        revision_id=view.revision_id,
        schema_fingerprint=view.schema_fingerprint,
        package_version=view.package_version,
        package_readiness=view.package_readiness,  # type: ignore[arg-type]
        activated_at=view.activated_at,
    )


@activations_router.get("", response_model=list[CatalogActivationEventSummary])
def list_activations(
    source_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> list[CatalogActivationEventSummary]:
    """List append-only activation history (newest first)."""
    events = list_activation_events(
        session,
        source_name=source_name,
        limit=limit,
        offset=offset,
    )
    return [
        CatalogActivationEventSummary(
            source_name=event.source_name,
            previous_revision_id=event.previous_revision_id,
            activated_revision_id=event.activated_revision_id,
            activated_at=event.activated_at,
        )
        for event in events
    ]


def activation_http_error(exc: CatalogActivationError) -> HTTPException:
    return build_public_http_error(
        error_code=exc.code,
        contracts=_ACTIVATION_PUBLIC_ERRORS,
        fallback_code=CatalogActivationErrorCode.INTERNAL_ERROR,
        fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        fallback_message="catalog activation operation failed",
    )
