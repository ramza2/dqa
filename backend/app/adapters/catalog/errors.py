"""Structured errors for Catalog Package validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogPackageIssue:
    """Single structured validation issue (safe for API responses)."""

    code: str
    message: str
    path: str | None = None


class CatalogPackageValidationError(Exception):
    """Raised when an uploaded Catalog Package fails deterministic validation."""

    def __init__(self, code: str, message: str, *, path: str | None = None) -> None:
        self.issue = CatalogPackageIssue(code=code, message=message, path=path)
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code

    @property
    def path(self) -> str | None:
        return self.issue.path


# Stable machine-readable codes (do not embed secrets or raw file bodies).
class CatalogPackageErrorCode:
    INVALID_ZIP = "CATALOG_PACKAGE_INVALID_ZIP"
    ARCHIVE_TOO_LARGE = "CATALOG_PACKAGE_ARCHIVE_TOO_LARGE"
    TOO_MANY_ENTRIES = "CATALOG_PACKAGE_TOO_MANY_ENTRIES"
    UNCOMPRESSED_TOO_LARGE = "CATALOG_PACKAGE_UNCOMPRESSED_TOO_LARGE"
    COMPRESSION_RATIO = "CATALOG_PACKAGE_COMPRESSION_RATIO"
    UNSAFE_PATH = "CATALOG_PACKAGE_UNSAFE_PATH"
    INVALID_ROOT = "CATALOG_PACKAGE_INVALID_ROOT"
    DUPLICATE_ENTRY = "CATALOG_PACKAGE_DUPLICATE_ENTRY"
    NON_REGULAR_ENTRY = "CATALOG_PACKAGE_NON_REGULAR_ENTRY"
    UNEXPECTED_FILE = "CATALOG_PACKAGE_UNEXPECTED_FILE"
    MISSING_MANIFEST = "CATALOG_PACKAGE_MISSING_MANIFEST"
    MALFORMED_MANIFEST = "CATALOG_PACKAGE_MALFORMED_MANIFEST"
    INVALID_PACKAGE_FORMAT = "CATALOG_PACKAGE_INVALID_FORMAT"
    UNSUPPORTED_VERSION = "CATALOG_PACKAGE_UNSUPPORTED_VERSION"
    INVALID_READINESS = "CATALOG_PACKAGE_INVALID_READINESS"
    MISSING_SOURCE = "CATALOG_PACKAGE_MISSING_SOURCE"
    MISSING_FINGERPRINT = "CATALOG_PACKAGE_MISSING_FINGERPRINT"
    INVALID_MANIFEST_FILES = "CATALOG_PACKAGE_INVALID_MANIFEST_FILES"
    MISSING_REQUIRED_FILE = "CATALOG_PACKAGE_MISSING_REQUIRED_FILE"
    CHECKSUM_MISMATCH = "CATALOG_PACKAGE_CHECKSUM_MISMATCH"
    BYTES_MISMATCH = "CATALOG_PACKAGE_BYTES_MISMATCH"
    MALFORMED_JSON = "CATALOG_PACKAGE_MALFORMED_JSON"
    SOURCE_MISMATCH = "CATALOG_PACKAGE_SOURCE_MISMATCH"
    FINGERPRINT_MISMATCH = "CATALOG_PACKAGE_FINGERPRINT_MISMATCH"
    COUNTS_MISMATCH = "CATALOG_PACKAGE_COUNTS_MISMATCH"
    EMPTY_UPLOAD = "CATALOG_PACKAGE_EMPTY_UPLOAD"
