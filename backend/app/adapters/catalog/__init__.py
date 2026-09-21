"""Catalog Package adapters (ZIP reader / validation helpers)."""

from app.adapters.catalog.errors import CatalogPackageValidationError
from app.adapters.catalog.package_reader import read_safe_package_archive
from app.adapters.catalog.limits import DEFAULT_ZIP_LIMITS, PACKAGE_FORMAT, PACKAGE_ROOT_NAME

__all__ = [
    "CatalogPackageValidationError",
    "DEFAULT_ZIP_LIMITS",
    "PACKAGE_FORMAT",
    "PACKAGE_ROOT_NAME",
    "read_safe_package_archive",
]
