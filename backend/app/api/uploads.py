"""Shared multipart upload helpers for Catalog Package endpoints."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile, status

from app.adapters.catalog.limits import DEFAULT_ZIP_LIMITS
from app.schemas.catalog_package import CatalogPackageErrorBody


async def read_upload_bounded(upload: UploadFile) -> bytes:
    """Read an uploaded ZIP while enforcing the compressed-size limit."""
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
