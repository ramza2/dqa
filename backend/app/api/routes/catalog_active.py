"""Active Catalog and activation-history query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import (
    CatalogActivationError,
    CatalogActivationErrorCode,
)
from app.adapters.db.deps import get_db_session
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


@active_router.get("", response_model=list[CatalogActiveSummary])
def list_active(
    session: Session = Depends(get_db_session),
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
    if exc.code == CatalogActivationErrorCode.IMPORT_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == CatalogActivationErrorCode.ACTIVE_REVISION_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE:
        status_code = status.HTTP_409_CONFLICT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )
