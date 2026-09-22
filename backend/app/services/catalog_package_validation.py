"""Catalog Package v2 validation orchestration (no DB persistence)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.adapters.catalog.errors import CatalogPackageErrorCode, CatalogPackageValidationError
from app.adapters.catalog.limits import (
    DEFAULT_ZIP_LIMITS,
    MANIFEST_FILENAME,
    NON_CANONICAL_ARTIFACT_SUFFIXES,
    PACKAGE_FORMAT,
    REQUIRED_RUNTIME_JSON_FILES,
    SUPPORTED_PACKAGE_MAJOR_VERSION,
    CatalogPackageZipLimits,
)
from app.adapters.catalog.package_reader import (
    SafePackageArchive,
    read_safe_package_archive,
    sha256_hex,
)
from app.schemas.catalog_package import (
    CatalogPackageManifest,
    CategoriesDocument,
    ColumnsDocument,
    DatabaseDocument,
    DiffLatestDocument,
    ErdDocument,
    IndexesDocument,
    LatestRunDocument,
    PackageReadiness,
    PackageSourceIdentity,
    PreflightDocument,
    RelationsDocument,
    SchemaSnapshotDocument,
    TablesDocument,
)

_REQUIRED_DOCUMENT_MODELS: dict[str, type[BaseModel]] = {
    "database.json": DatabaseDocument,
    "tables.json": TablesDocument,
    "columns.json": ColumnsDocument,
    "relations.json": RelationsDocument,
    "indexes.json": IndexesDocument,
    "categories.json": CategoriesDocument,
    "erd.json": ErdDocument,
    "analysis/latest_run.json": LatestRunDocument,
    "analysis/schema_snapshot.json": SchemaSnapshotDocument,
    "validation/preflight.json": PreflightDocument,
    "diff/latest.json": DiffLatestDocument,
}


@dataclass(frozen=True)
class ValidatedCatalogPackage:
    """Service-level validation result reusable by future import persistence.

    This object is intentionally richer than the HTTP response so PR 4 can
    persist digests/parsed core JSON without re-validating the archive.
    """

    archive_sha256: str
    manifest_sha256: str
    package_format: str
    package_version: str
    package_readiness: PackageReadiness
    activation_eligible: bool
    source: PackageSourceIdentity
    schema_fingerprint: str
    counts: dict[str, Any]
    files_validated: int
    warnings: tuple[str, ...] = ()
    managed_file_digests: dict[str, str] = field(default_factory=dict)
    parsed_documents: dict[str, Any] = field(default_factory=dict)


def validate_catalog_package_bytes(
    archive_bytes: bytes,
    *,
    limits: CatalogPackageZipLimits = DEFAULT_ZIP_LIMITS,
) -> ValidatedCatalogPackage:
    """Validate a Catalog Package v2 ZIP in memory and return a typed result."""
    archive = read_safe_package_archive(archive_bytes, limits=limits)
    return validate_safe_package_archive(archive, limits=limits)


def validate_safe_package_archive(
    archive: SafePackageArchive,
    *,
    limits: CatalogPackageZipLimits = DEFAULT_ZIP_LIMITS,
) -> ValidatedCatalogPackage:
    manifest_entry = archive.files[MANIFEST_FILENAME]
    if manifest_entry.size > limits.max_manifest_bytes:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.MALFORMED_MANIFEST,
            "manifest.json exceeds maximum allowed size",
            path=MANIFEST_FILENAME,
        )

    manifest = _parse_manifest(manifest_entry.data)
    _validate_package_identity(manifest)
    _validate_manifest_files(archive, manifest)

    # Unexpected unmanaged files (except manifest itself).
    managed_paths = {entry.path for entry in manifest.files}
    for relative_path in archive.files:
        if relative_path == MANIFEST_FILENAME:
            continue
        if relative_path not in managed_paths:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.UNEXPECTED_FILE,
                "file is not declared in manifest.files",
                path=relative_path,
            )

    # Required runtime JSON presence (must also be manifest-managed).
    for required in REQUIRED_RUNTIME_JSON_FILES:
        if required not in archive.files:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.MISSING_REQUIRED_FILE,
                "required runtime JSON file is missing",
                path=required,
            )
        if required not in managed_paths:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.MISSING_REQUIRED_FILE,
                "required runtime JSON file is not declared in manifest.files",
                path=required,
            )

    parsed_documents = _parse_required_json_documents(archive)
    warnings = _cross_check_consistency(manifest, parsed_documents)

    readiness = manifest.package_readiness
    activation_eligible = readiness == "READY"

    digests = {
        path: entry.sha256
        for path, entry in archive.files.items()
        if path == MANIFEST_FILENAME or path in managed_paths
    }

    return ValidatedCatalogPackage(
        archive_sha256=archive.archive_sha256,
        manifest_sha256=manifest_entry.sha256,
        package_format=manifest.package_format,
        package_version=manifest.package_version,
        package_readiness=readiness,
        activation_eligible=activation_eligible,
        source=manifest.source,
        schema_fingerprint=manifest.schema_fingerprint,
        counts=dict(manifest.counts or {}),
        files_validated=len(manifest.files),
        warnings=tuple(warnings),
        managed_file_digests=digests,
        parsed_documents=parsed_documents,
    )


def _parse_manifest(data: bytes) -> CatalogPackageManifest:
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.MALFORMED_MANIFEST,
            "manifest.json is not valid UTF-8 JSON",
            path=MANIFEST_FILENAME,
        ) from exc

    try:
        return CatalogPackageManifest.model_validate(payload)
    except ValidationError as exc:
        # Do not echo raw field values (may include secret-like strings).
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.MALFORMED_MANIFEST,
            "manifest.json failed structural validation",
            path=MANIFEST_FILENAME,
        ) from exc


def _validate_package_identity(manifest: CatalogPackageManifest) -> None:
    if manifest.package_format != PACKAGE_FORMAT:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.INVALID_PACKAGE_FORMAT,
            "unsupported package_format",
            path=MANIFEST_FILENAME,
        )

    major = _package_major_version(manifest.package_version)
    if major != SUPPORTED_PACKAGE_MAJOR_VERSION:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSUPPORTED_VERSION,
            "unsupported package_version major",
            path=MANIFEST_FILENAME,
        )

    if manifest.package_readiness not in ("READY", "WARNING", "BLOCKED"):
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.INVALID_READINESS,
            "package_readiness must be READY, WARNING, or BLOCKED",
            path=MANIFEST_FILENAME,
        )


def _package_major_version(version: str) -> int:
    cleaned = version.strip()
    if not cleaned:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSUPPORTED_VERSION,
            "package_version is empty",
            path=MANIFEST_FILENAME,
        )
    head = cleaned.split(".", 1)[0]
    if not head.isdigit():
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.UNSUPPORTED_VERSION,
            "package_version major is not numeric",
            path=MANIFEST_FILENAME,
        )
    return int(head)


def _validate_manifest_files(
    archive: SafePackageArchive,
    manifest: CatalogPackageManifest,
) -> None:
    if not manifest.files:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.INVALID_MANIFEST_FILES,
            "manifest.files must contain at least one managed file",
            path=MANIFEST_FILENAME,
        )

    seen_paths: set[str] = set()
    for entry in manifest.files:
        if entry.path == MANIFEST_FILENAME:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.INVALID_MANIFEST_FILES,
                "manifest.json must not list itself in manifest.files",
                path=entry.path,
            )
        if entry.path in seen_paths:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.INVALID_MANIFEST_FILES,
                "duplicate path in manifest.files",
                path=entry.path,
            )
        seen_paths.add(entry.path)

        file_entry = archive.files.get(entry.path)
        if file_entry is None:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.MISSING_REQUIRED_FILE,
                "manifest-managed file is missing from archive",
                path=entry.path,
            )

        if file_entry.size != entry.bytes:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.BYTES_MISMATCH,
                "file size does not match manifest bytes",
                path=entry.path,
            )
        if file_entry.sha256 != entry.sha256.lower():
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.CHECKSUM_MISMATCH,
                "file SHA-256 does not match manifest",
                path=entry.path,
            )


def _parse_required_json_documents(archive: SafePackageArchive) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for relative_path in REQUIRED_RUNTIME_JSON_FILES:
        entry = archive.files[relative_path]
        if relative_path.endswith(NON_CANONICAL_ARTIFACT_SUFFIXES):
            continue
        try:
            payload = json.loads(entry.data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.MALFORMED_JSON,
                "required JSON file is not valid UTF-8 JSON",
                path=relative_path,
            ) from exc
        parsed[relative_path] = payload

    for relative_path, model_cls in _REQUIRED_DOCUMENT_MODELS.items():
        try:
            model_cls.model_validate(parsed[relative_path])
        except ValidationError as exc:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.MALFORMED_JSON,
                f"{relative_path} failed structural validation",
                path=relative_path,
            ) from exc

    return parsed


def _cross_check_consistency(
    manifest: CatalogPackageManifest,
    parsed: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []

    database = DatabaseDocument.model_validate(parsed["database.json"])
    _assert_source_match(manifest.source, database.source, path="database.json")

    db_fp = _extract_fingerprint_from_latest_analysis(database.latest_analysis)
    if db_fp is None:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.FINGERPRINT_MISMATCH,
            "database.json latest_analysis.schema_fingerprint is missing",
            path="database.json",
        )
    if db_fp != manifest.schema_fingerprint:
        raise CatalogPackageValidationError(
            CatalogPackageErrorCode.FINGERPRINT_MISMATCH,
            "schema_fingerprint mismatch between manifest and database.json",
            path="database.json",
        )

    run_doc = LatestRunDocument.model_validate(parsed["analysis/latest_run.json"])
    run_fp = _extract_latest_run_fingerprint(run_doc)
    if run_doc.available:
        if run_fp is None:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.FINGERPRINT_MISMATCH,
                "analysis/latest_run.json run.schema_fingerprint is missing",
                path="analysis/latest_run.json",
            )
        if run_fp != manifest.schema_fingerprint:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.FINGERPRINT_MISMATCH,
                "schema_fingerprint mismatch between manifest and analysis/latest_run.json",
                path="analysis/latest_run.json",
            )

    _assert_counts(manifest.counts, parsed)
    return warnings


def _assert_source_match(
    expected: PackageSourceIdentity,
    actual: PackageSourceIdentity,
    *,
    path: str,
) -> None:
    """Fields present on the manifest source must match database.json source exactly.

    Optional manifest fields that are null/absent are not required on database.json.
    """
    for field_name in ("source_name", "db_type", "database_name", "default_schema"):
        left = getattr(expected, field_name)
        if left is None:
            continue
        right = getattr(actual, field_name)
        if right is None or right != left:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.SOURCE_MISMATCH,
                f"source.{field_name} mismatch between manifest and {path}",
                path=path,
            )


def _extract_fingerprint_from_latest_analysis(latest_analysis: dict[str, Any] | None) -> str | None:
    if not isinstance(latest_analysis, dict):
        return None
    value = latest_analysis.get("schema_fingerprint")
    return value if isinstance(value, str) and value.strip() else None


def _extract_latest_run_fingerprint(doc: LatestRunDocument) -> str | None:
    if not isinstance(doc.run, dict):
        return None
    value = doc.run.get("schema_fingerprint")
    return value if isinstance(value, str) and value.strip() else None


def _assert_counts(counts: dict[str, Any], parsed: dict[str, Any]) -> None:
    if not counts:
        return

    mapping = {
        "tables": ("tables.json", ("tables",)),
        "columns": ("columns.json", ("columns",)),
        "relations": ("relations.json", ("relations",)),
        "indexes": ("indexes.json", ("indexes",)),
        "categories": ("categories.json", ("categories",)),
    }
    for count_key, (file_name, list_keys) in mapping.items():
        if count_key not in counts:
            continue
        declared = counts[count_key]
        if not isinstance(declared, int):
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.COUNTS_MISMATCH,
                f"manifest.counts.{count_key} must be an integer",
                path=MANIFEST_FILENAME,
            )
        actual = _count_items(parsed[file_name], list_keys)
        if actual is None:
            continue
        if actual != declared:
            raise CatalogPackageValidationError(
                CatalogPackageErrorCode.COUNTS_MISMATCH,
                f"manifest.counts.{count_key} does not match {file_name} item count",
                path=file_name,
            )


def _count_items(payload: Any, preferred_keys: tuple[str, ...]) -> int | None:
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for key in preferred_keys:
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return None


# Re-export helper for tests / future import PR.
__all__ = [
    "ValidatedCatalogPackage",
    "validate_catalog_package_bytes",
    "validate_safe_package_archive",
    "sha256_hex",
]
