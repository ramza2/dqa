"""Catalog import history query endpoints (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.api.routes.catalog_packages import to_detail
from app.schemas.catalog_package import CatalogImportRevisionDetail, CatalogImportRevisionSummary
from app.services.catalog_package_import import get_catalog_import, list_catalog_imports

router = APIRouter(prefix="/api/v1/catalog/imports", tags=["catalog-imports"])


@router.get("", response_model=list[CatalogImportRevisionSummary])
def list_imports(
    source_name: str | None = Query(default=None),
    package_readiness: str | None = Query(default=None),
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
    return [
        CatalogImportRevisionSummary(
            id=row.id,
            source_name=row.source_name,
            db_type=row.db_type,
            database_name=row.database_name,
            default_schema=row.default_schema,
            package_format=row.package_format,
            package_version=row.package_version,
            package_readiness=row.package_readiness,  # type: ignore[arg-type]
            activation_eligible=row.package_readiness == "READY",
            schema_fingerprint=row.schema_fingerprint,
            archive_sha256=row.archive_sha256,
            manifest_sha256=row.manifest_sha256,
            validation_status=row.validation_status,
            generated_at=row.generated_at,
            imported_at=row.imported_at,
            table_count=row.table_count,
            column_count=row.column_count,
            relation_count=row.relation_count,
            index_count=row.index_count,
            category_count=row.category_count,
            category_assignment_count=row.category_assignment_count,
            managed_file_count=row.managed_file_count,
            created=None,
        )
        for row in revisions
    ]


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
