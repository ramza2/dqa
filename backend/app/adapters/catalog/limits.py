"""Catalog Package ZIP size and expansion limits (single source of truth)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogPackageZipLimits:
    """Operational defaults for untrusted Catalog Package ZIP inspection.

    Values are intentionally generous for real packages while still bounding
    zip-bomb / resource-exhaustion attacks. Keep all magic numbers here.
    """

    # Compressed upload / archive size.
    max_archive_bytes: int = 50 * 1024 * 1024  # 50 MiB

    # Entry budget (files + directories).
    max_entry_count: int = 512

    # Uncompressed expansion budget.
    max_uncompressed_total_bytes: int = 200 * 1024 * 1024  # 200 MiB
    max_uncompressed_file_bytes: int = 64 * 1024 * 1024  # 64 MiB

    # uncompressed_size / compressed_size upper bound (stored entries skipped).
    max_compression_ratio: float = 100.0

    # Manifest itself is small JSON; reject absurd sizes early.
    max_manifest_bytes: int = 2 * 1024 * 1024  # 2 MiB


DEFAULT_ZIP_LIMITS = CatalogPackageZipLimits()

PACKAGE_ROOT_NAME = "demis_catalog_package"
PACKAGE_FORMAT = "demis-catalog-package"
SUPPORTED_PACKAGE_MAJOR_VERSION = 2

MANIFEST_FILENAME = "manifest.json"

# Runtime-required JSON relative to package root (docs/catalog-package-contract.md).
REQUIRED_RUNTIME_JSON_FILES: tuple[str, ...] = (
    "database.json",
    "tables.json",
    "columns.json",
    "relations.json",
    "indexes.json",
    "categories.json",
    "erd.json",
    "analysis/latest_run.json",
    "analysis/schema_snapshot.json",
    "validation/preflight.json",
    "diff/latest.json",
)

# Human-readable / supplemental artifacts — never treated as canonical catalog facts.
NON_CANONICAL_ARTIFACT_SUFFIXES: tuple[str, ...] = (
    ".md",
    ".docx",
)
