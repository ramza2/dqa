"""Catalog Package upload validation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.adapters.catalog.errors import CatalogPackageValidationError
from app.adapters.catalog.limits import DEFAULT_ZIP_LIMITS
from app.schemas.catalog_package import CatalogPackageErrorBody, CatalogPackageValidateResponse
from app.services.catalog_package_validation import validate_catalog_package_bytes

router = APIRouter(prefix="/api/v1/catalog/packages", tags=["catalog-packages"])


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
) -> CatalogPackageValidateResponse:
    """Validate an uploaded Catalog Package v2 ZIP without persisting it."""
    archive_bytes = await _read_upload_bounded(file)
    try:
        result = validate_catalog_package_bytes(archive_bytes)
    except CatalogPackageValidationError as exc:
        status_code = status.HTTP_400_BAD_REQUEST
        if exc.code in {
            "CATALOG_PACKAGE_ARCHIVE_TOO_LARGE",
            "CATALOG_PACKAGE_UNCOMPRESSED_TOO_LARGE",
            "CATALOG_PACKAGE_TOO_MANY_ENTRIES",
        }:
            status_code = status.HTTP_413_CONTENT_TOO_LARGE
        raise HTTPException(
            status_code=status_code,
            detail=CatalogPackageErrorBody(
                code=exc.code,
                message=exc.issue.message,
                path=exc.path,
            ).model_dump(),
        ) from exc

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


async def _read_upload_bounded(upload: UploadFile) -> bytes:
    max_bytes = DEFAULT_ZIP_LIMITS.max_archive_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=CatalogPackageErrorBody(
                    code="CATALOG_PACKAGE_ARCHIVE_TOO_LARGE",
                    message="archive exceeds maximum allowed compressed size",
                ).model_dump(),
            )
        chunks.append(chunk)
    return b"".join(chunks)
