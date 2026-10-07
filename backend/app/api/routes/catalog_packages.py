"""Catalog Package upload validation and import endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.adapters.catalog.errors import (
    CatalogPackageErrorCode,
    CatalogPackageValidationError,
)
from app.adapters.db.deps import get_db_session
from app.api.uploads import read_upload_bounded
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.models.catalog_import import CatalogImportRevision
from app.schemas.catalog_package import (
    CatalogImportResult,
    CatalogImportRevisionDetail,
    CatalogImportRevisionSummary,
    CatalogPackageErrorBody,
    CatalogPackageValidateResponse,
)
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.catalog_package_validation import validate_catalog_package_bytes

router = APIRouter(prefix="/api/v1/catalog/packages", tags=["catalog-packages"])

_CATALOG_PACKAGE_PUBLIC_CODES = frozenset(
    {
        CatalogPackageErrorCode.INVALID_ZIP,
        CatalogPackageErrorCode.ARCHIVE_TOO_LARGE,
        CatalogPackageErrorCode.TOO_MANY_ENTRIES,
        CatalogPackageErrorCode.UNCOMPRESSED_TOO_LARGE,
        CatalogPackageErrorCode.COMPRESSION_RATIO,
        CatalogPackageErrorCode.UNSAFE_PATH,
        CatalogPackageErrorCode.INVALID_ROOT,
        CatalogPackageErrorCode.DUPLICATE_ENTRY,
        CatalogPackageErrorCode.NON_REGULAR_ENTRY,
        CatalogPackageErrorCode.UNEXPECTED_FILE,
        CatalogPackageErrorCode.MISSING_MANIFEST,
        CatalogPackageErrorCode.MALFORMED_MANIFEST,
        CatalogPackageErrorCode.INVALID_PACKAGE_FORMAT,
        CatalogPackageErrorCode.UNSUPPORTED_VERSION,
        CatalogPackageErrorCode.INVALID_READINESS,
        CatalogPackageErrorCode.MISSING_SOURCE,
        CatalogPackageErrorCode.MISSING_FINGERPRINT,
        CatalogPackageErrorCode.INVALID_MANIFEST_FILES,
        CatalogPackageErrorCode.MISSING_REQUIRED_FILE,
        CatalogPackageErrorCode.CHECKSUM_MISMATCH,
        CatalogPackageErrorCode.BYTES_MISMATCH,
        CatalogPackageErrorCode.MALFORMED_JSON,
        CatalogPackageErrorCode.SOURCE_MISMATCH,
        CatalogPackageErrorCode.FINGERPRINT_MISMATCH,
        CatalogPackageErrorCode.COUNTS_MISMATCH,
        CatalogPackageErrorCode.EMPTY_UPLOAD,
        CatalogPackageErrorCode.FORBIDDEN_SECRET_FIELD,
    }
)

_CATALOG_PACKAGE_TOO_LARGE_CODES = frozenset(
    {
        CatalogPackageErrorCode.ARCHIVE_TOO_LARGE,
        CatalogPackageErrorCode.UNCOMPRESSED_TOO_LARGE,
        CatalogPackageErrorCode.TOO_MANY_ENTRIES,
    }
)


@router.post(
    "/validate",
    response_model=CatalogPackageValidateResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": CatalogPackageErrorBody},
        status.HTTP_413_CONTENT_TOO_LARGE: {"model": CatalogPackageErrorBody},
    },
)
async def validate_catalog_package(
    file: UploadFile = File(..., description="Catalog Package v2 ZIP archive"),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> CatalogPackageValidateResponse:
    """Validate an uploaded Catalog Package v2 ZIP without persisting it."""
    archive_bytes = await read_upload_bounded(file)
    try:
        result = validate_catalog_package_bytes(archive_bytes)
    except CatalogPackageValidationError as exc:
        raise _validation_http_error(exc) from exc

    return CatalogPackageValidateResponse(
        valid=True,
        package_format=result.package_format,
        package_version=result.package_version,
        package_readiness=result.package_readiness,
        activation_eligible=result.activation_eligible,
        source=result.source,
        schema_fingerprint=result.schema_fingerprint,
        archive_sha256=result.archive_sha256,
        manifest_sha256=result.manifest_sha256,
        counts=result.counts,
        files_validated=result.files_validated,
        warnings=list(result.warnings),
        errors=[],
    )


@router.post(
    "/import",
    response_model=CatalogImportResult,
    responses={
        status.HTTP_400_BAD_REQUEST: {"model": CatalogPackageErrorBody},
        status.HTTP_413_CONTENT_TOO_LARGE: {"model": CatalogPackageErrorBody},
    },
)
async def import_catalog_package(
    file: UploadFile = File(..., description="Catalog Package v2 ZIP archive"),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> CatalogImportResult:
    """Validate and persist an immutable Catalog Package import revision."""
    archive_bytes = await read_upload_bounded(file)
    try:
        revision, created = import_catalog_package_bytes(archive_bytes, session)
    except CatalogPackageValidationError as exc:
        raise _validation_http_error(exc) from exc
    return to_import_result(revision, created=created)


def _validation_http_error(exc: CatalogPackageValidationError) -> HTTPException:
    if exc.code not in _CATALOG_PACKAGE_PUBLIC_CODES:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=CatalogPackageErrorBody(
                code=CatalogPackageErrorCode.INTERNAL_ERROR,
                message="catalog package validation failed",
                path=None,
            ).model_dump(),
        )

    status_code = (
        status.HTTP_413_CONTENT_TOO_LARGE
        if exc.code in _CATALOG_PACKAGE_TOO_LARGE_CODES
        else status.HTTP_400_BAD_REQUEST
    )
    # The code/path are public only after the code passed the reviewed allowlist
    # above. Copy them out before constructing HTTPException.detail so route
    # error payloads never consume typed-exception state directly.
    public_code = exc.code
    public_path = exc.path
    return HTTPException(
        status_code=status_code,
        detail=CatalogPackageErrorBody(
            code=public_code,
            message="catalog package validation failed",
            path=public_path,
        ).model_dump(),
    )


def to_summary(revision: CatalogImportRevision) -> CatalogImportRevisionSummary:
    return CatalogImportRevisionSummary(
        id=revision.id,
        source_name=revision.source_name,
        db_type=revision.db_type,
        database_name=revision.database_name,
        default_schema=revision.default_schema,
        package_format=revision.package_format,
        package_version=revision.package_version,
        package_readiness=revision.package_readiness,  # type: ignore[arg-type]
        activation_eligible=revision.package_readiness == "READY",
        schema_fingerprint=revision.schema_fingerprint,
        archive_sha256=revision.archive_sha256,
        manifest_sha256=revision.manifest_sha256,
        validation_status=revision.validation_status,
        generated_at=revision.generated_at,
        imported_at=revision.imported_at,
        table_count=revision.table_count,
        column_count=revision.column_count,
        relation_count=revision.relation_count,
        index_count=revision.index_count,
        category_count=revision.category_count,
        category_assignment_count=revision.category_assignment_count,
        managed_file_count=revision.managed_file_count,
    )


def to_import_result(revision: CatalogImportRevision, *, created: bool) -> CatalogImportResult:
    return CatalogImportResult(**to_summary(revision).model_dump(), created=created)


def to_detail(revision: CatalogImportRevision) -> CatalogImportRevisionDetail:
    return CatalogImportRevisionDetail(
        **to_summary(revision).model_dump(),
        created_at=revision.created_at,
    )
