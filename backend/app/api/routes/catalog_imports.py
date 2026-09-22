"""Catalog import history query endpoints (read-only) and activation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import CatalogActivationError
from app.adapters.db.deps import get_db_session
from app.api.routes.catalog_active import activation_http_error
from app.api.routes.catalog_packages import to_detail, to_summary
from app.schemas.catalog_package import (
    CatalogActivateResult,
    CatalogImportRevisionDetail,
    CatalogImportRevisionSummary,
    PackageReadiness,
)
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import get_catalog_import, list_catalog_imports

router = APIRouter(prefix="/api/v1/catalog/imports", tags=["catalog-imports"])


@router.get("", response_model=list[CatalogImportRevisionSummary])
def list_imports(
    source_name: str | None = Query(default=None),
    package_readiness: PackageReadiness | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> list[CatalogImportRevisionSummary]:
    """List immutable Catalog Package import revisions (newest first)."""
    revisions = list_catalog_imports(
        session,
        source_name=source_name,
        package_readiness=package_readiness,
        limit=limit,
        offset=offset,
    )
    return [to_summary(row) for row in revisions]


@router.post(
    "/{revision_id}/activate",
    response_model=CatalogActivateResult,
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Import revision not found"},
        status.HTTP_409_CONFLICT: {"description": "Revision not activatable"},
    },
)
def activate_import(
    revision_id: int,
    session: Session = Depends(get_db_session),
) -> CatalogActivateResult:
    """Activate a READY+VALID import revision (source_name taken from the revision)."""
    try:
        result = activate_catalog_revision(session, revision_id)
    except CatalogActivationError as exc:
        raise activation_http_error(exc) from exc
    return CatalogActivateResult(
        source_name=result.source_name,
        active_revision_id=result.active_revision_id,
        previous_revision_id=result.previous_revision_id,
        schema_fingerprint=result.schema_fingerprint,
        package_readiness=result.package_readiness,  # type: ignore[arg-type]
        package_version=result.package_version,
        activated_at=result.activated_at,
        changed=result.changed,
    )


@router.get("/{revision_id}", response_model=CatalogImportRevisionDetail)
def get_import(
    revision_id: int,
    session: Session = Depends(get_db_session),
) -> CatalogImportRevisionDetail:
    """Return metadata for one Catalog Package import revision."""
    revision = get_catalog_import(session, revision_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CATALOG_IMPORT_NOT_FOUND", "message": "import revision not found"},
        )
    return to_detail(revision)
