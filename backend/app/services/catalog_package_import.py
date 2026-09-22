"""Catalog Package import orchestration (validate then persist immutable revision)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.catalog.limits import CatalogPackageZipLimits, DEFAULT_ZIP_LIMITS
from app.models.catalog_import import CatalogImportRevision
from app.repositories.catalog_import import CatalogImportRepository
from app.services.catalog_package_validation import (
    ValidatedCatalogPackage,
    validate_catalog_package_bytes,
)


def import_catalog_package_bytes(
    archive_bytes: bytes,
    session: Session,
    *,
    limits: CatalogPackageZipLimits = DEFAULT_ZIP_LIMITS,
) -> tuple[CatalogImportRevision, bool]:
    """Validate then persist a Catalog Package import revision.

    Returns:
        (revision, created) where created is False when an existing row with the
        same archive_sha256 was returned (deduplicated).
    """
    validated = validate_catalog_package_bytes(archive_bytes, limits=limits)
    return persist_validated_catalog_package(validated, session)


def persist_validated_catalog_package(
    validated: ValidatedCatalogPackage,
    session: Session,
) -> tuple[CatalogImportRevision, bool]:
    """Persist a previously validated package. Does not re-parse the ZIP."""
    repo = CatalogImportRepository(session)

    existing = repo.get_by_archive_sha256(validated.archive_sha256)
    if existing is not None:
        return existing, False

    revision = _build_revision(validated)
    try:
        saved = repo.add(revision)
        return saved, True
    except IntegrityError:
        # Concurrent duplicate insert on unique archive_sha256.
        session.rollback()
        existing = repo.get_by_archive_sha256(validated.archive_sha256)
        if existing is None:
            raise
        return existing, False


def list_catalog_imports(
    session: Session,
    *,
    source_name: str | None = None,
    package_readiness: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CatalogImportRevision]:
    return CatalogImportRepository(session).list_revisions(
        source_name=source_name,
        package_readiness=package_readiness,
        limit=limit,
        offset=offset,
    )


def get_catalog_import(session: Session, revision_id: int) -> CatalogImportRevision | None:
    return CatalogImportRepository(session).get_by_id(revision_id)


def _build_revision(validated: ValidatedCatalogPackage) -> CatalogImportRevision:
    docs = validated.parsed_documents
    counts = validated.counts or {}

    table_count = _as_int_count(counts.get("tables"), docs.get("tables.json"), "tables")
    column_count = _as_int_count(counts.get("columns"), docs.get("columns.json"), "columns")
    relation_count = _as_int_count(counts.get("relations"), docs.get("relations.json"), "relations")
    index_count = _as_int_count(counts.get("indexes"), docs.get("indexes.json"), "indexes")
    category_count = _as_int_count(counts.get("categories"), docs.get("categories.json"), "categories")
    category_assignment_count = _assignment_count(docs.get("categories.json"))

    return CatalogImportRevision(
        source_name=validated.source.source_name,
        db_type=validated.source.db_type,
        database_name=validated.source.database_name,
        default_schema=validated.source.default_schema,
        package_format=validated.package_format,
        package_version=validated.package_version,
        package_readiness=validated.package_readiness,
        schema_fingerprint=validated.schema_fingerprint,
        archive_sha256=validated.archive_sha256,
        manifest_sha256=validated.manifest_sha256,
        generated_at=validated.generated_at,
        imported_at=datetime.now(timezone.utc),
        validation_status="VALID",
        table_count=table_count,
        column_count=column_count,
        relation_count=relation_count,
        index_count=index_count,
        category_count=category_count,
        category_assignment_count=category_assignment_count,
        managed_file_count=validated.files_validated,
        manifest_json=dict(validated.manifest_document),
        database_json=_as_object(docs["database.json"]),
        tables_json=_as_object(docs["tables.json"]),
        columns_json=_as_object(docs["columns.json"]),
        relations_json=_as_object(docs["relations.json"]),
        indexes_json=_as_object(docs["indexes.json"]),
        categories_json=_as_object(docs["categories.json"]),
        erd_json=_as_object(docs["erd.json"]),
        latest_run_json=_as_object(docs["analysis/latest_run.json"]),
        schema_snapshot_json=_as_object(docs["analysis/schema_snapshot.json"]),
        preflight_json=_as_object(docs["validation/preflight.json"]),
        latest_diff_json=_as_object(docs["diff/latest.json"]),
        managed_file_digests_json=dict(validated.managed_file_digests),
    )


def _as_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise TypeError("expected JSON object document")


def _as_int_count(declared: Any, document: Any, list_key: str) -> int:
    if isinstance(declared, int):
        return declared
    if isinstance(document, dict):
        items = document.get(list_key)
        if isinstance(items, list):
            return len(items)
    return 0


def _assignment_count(categories_doc: Any) -> int:
    if not isinstance(categories_doc, dict):
        return 0
    assignments = categories_doc.get("table_assignments")
    if isinstance(assignments, list):
        return len(assignments)
    return 0

