"""Catalog Package import persistence tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.catalog.errors import CatalogPackageErrorCode, CatalogPackageValidationError
from app.models.catalog_import import CatalogImportRevision
from app.services.catalog_package_import import (
    get_catalog_import,
    import_catalog_package_bytes,
    list_catalog_imports,
)
from app.services.catalog_package_validation import validate_catalog_package_bytes
from tests.catalog_package_fixtures import (
    DEFAULT_FINGERPRINT,
    DEFAULT_SOURCE,
    build_core_documents,
    build_manifest,
    build_package_zip,
)

pytestmark = pytest.mark.integration


def _count_rows(session: Session) -> int:
    return session.scalars(select(CatalogImportRevision)).all().__len__()


def test_import_ready_package_succeeds(db_session: Session) -> None:
    archive = build_package_zip(package_readiness="READY")
    validated = validate_catalog_package_bytes(archive)
    revision, created = import_catalog_package_bytes(archive, db_session)
    assert created is True
    assert revision.id is not None
    assert revision.package_readiness == "READY"
    assert revision.archive_sha256 == validated.archive_sha256
    assert revision.manifest_sha256 == validated.manifest_sha256
    assert revision.schema_fingerprint == validated.schema_fingerprint
    assert revision.table_count == validated.counts["tables"]
    assert revision.column_count == validated.counts["columns"]
    assert revision.relation_count == validated.counts["relations"]
    assert revision.index_count == validated.counts["indexes"]
    assert revision.category_count == validated.counts["categories"]
    assert revision.managed_file_count == validated.files_validated
    assert revision.validation_status == "VALID"
    assert revision.database_json == validated.parsed_documents["database.json"]
    assert revision.tables_json == validated.parsed_documents["tables.json"]
    assert revision.manifest_json["package_format"] == "demis-catalog-package"
    assert revision.package_readiness == "READY"


def test_import_warning_package_succeeds(db_session: Session) -> None:
    archive = build_package_zip(package_readiness="WARNING")
    revision, created = import_catalog_package_bytes(archive, db_session)
    assert created is True
    assert revision.package_readiness == "WARNING"


def test_import_blocked_package_succeeds_not_activation_eligible(
    db_session: Session, db_client: TestClient
) -> None:
    archive = build_package_zip(package_readiness="BLOCKED")
    revision, created = import_catalog_package_bytes(archive, db_session)
    assert created is True
    assert revision.package_readiness == "BLOCKED"
    db_session.commit()

    response = db_client.post(
        "/api/v1/catalog/packages/import",
        files={"file": ("pkg.zip", archive, "application/zip")},
    )
    # Same archive returns existing; activation_eligible must be false for BLOCKED.
    assert response.status_code == 200
    payload = response.json()
    assert payload["package_readiness"] == "BLOCKED"
    assert payload["activation_eligible"] is False
    assert payload["created"] is False


def test_invalid_package_does_not_create_db_row(db_session: Session) -> None:
    archive = build_package_zip(package_format="nope")
    before = _count_rows(db_session)
    with pytest.raises(CatalogPackageValidationError) as exc_info:
        import_catalog_package_bytes(archive, db_session)
    assert exc_info.value.code == CatalogPackageErrorCode.INVALID_PACKAGE_FORMAT
    assert _count_rows(db_session) == before


def test_duplicate_archive_sha256_returns_existing(db_session: Session) -> None:
    archive = build_package_zip(package_readiness="READY")
    first, created1 = import_catalog_package_bytes(archive, db_session)
    second, created2 = import_catalog_package_bytes(archive, db_session)
    assert created1 is True
    assert created2 is False
    assert first.id == second.id
    assert _count_rows(db_session) == 1


def test_same_fingerprint_different_archive_creates_new_revision(db_session: Session) -> None:
    files_a = build_core_documents(fingerprint=DEFAULT_FINGERPRINT)
    files_b = build_core_documents(fingerprint=DEFAULT_FINGERPRINT)
    # Change a non-canonical artifact so archive digest changes while fingerprint stays.
    files_b["PACKAGE_README.md"] = b"# Catalog Package variant\n"
    archive_a = build_package_zip(files=files_a, fingerprint=DEFAULT_FINGERPRINT)
    archive_b = build_package_zip(files=files_b, fingerprint=DEFAULT_FINGERPRINT)
    assert validate_catalog_package_bytes(archive_a).schema_fingerprint == DEFAULT_FINGERPRINT
    assert validate_catalog_package_bytes(archive_b).schema_fingerprint == DEFAULT_FINGERPRINT
    assert (
        validate_catalog_package_bytes(archive_a).archive_sha256
        != validate_catalog_package_bytes(archive_b).archive_sha256
    )

    first, _ = import_catalog_package_bytes(archive_a, db_session)
    second, created = import_catalog_package_bytes(archive_b, db_session)
    assert created is True
    assert first.id != second.id
    assert first.schema_fingerprint == second.schema_fingerprint
    assert _count_rows(db_session) == 2


def test_same_source_new_package_does_not_overwrite(db_session: Session) -> None:
    archive_a = build_package_zip(fingerprint="fp-a", mutate_files={"PACKAGE_README.md": b"A\n"})
    # Different fingerprint + content => new archive, same source_name.
    files = build_core_documents(fingerprint="fp-b")
    files["PACKAGE_README.md"] = b"B\n"
    archive_b = build_package_zip(files=files, fingerprint="fp-b")

    first, _ = import_catalog_package_bytes(archive_a, db_session)
    second, created = import_catalog_package_bytes(archive_b, db_session)
    assert created is True
    assert first.id != second.id
    assert first.source_name == second.source_name == DEFAULT_SOURCE["source_name"]
    # Original row unchanged.
    reloaded = get_catalog_import(db_session, first.id)
    assert reloaded is not None
    assert reloaded.schema_fingerprint == first.schema_fingerprint
    assert reloaded.archive_sha256 == first.archive_sha256


def test_import_history_newest_first(db_session: Session) -> None:
    a = build_package_zip(mutate_files={"PACKAGE_README.md": b"one\n"})
    b = build_package_zip(mutate_files={"PACKAGE_README.md": b"two\n"})
    first, _ = import_catalog_package_bytes(a, db_session)
    second, _ = import_catalog_package_bytes(b, db_session)
    rows = list_catalog_imports(db_session)
    assert [row.id for row in rows] == [second.id, first.id]


def test_import_history_source_name_filter(db_session: Session) -> None:
    archive = build_package_zip()
    import_catalog_package_bytes(archive, db_session)
    matched = list_catalog_imports(db_session, source_name=DEFAULT_SOURCE["source_name"])
    assert len(matched) == 1
    empty = list_catalog_imports(db_session, source_name="missing_source")
    assert empty == []


def test_unknown_import_id_returns_404(db_client: TestClient, db_session: Session) -> None:
    response = db_client.get("/api/v1/catalog/imports/999999")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "CATALOG_IMPORT_NOT_FOUND"


def test_import_api_persists_and_lists(db_client: TestClient, db_session: Session) -> None:
    archive = build_package_zip(package_readiness="READY")
    response = db_client.post(
        "/api/v1/catalog/packages/import",
        files={"file": ("pkg.zip", archive, "application/zip")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["created"] is True
    assert payload["activation_eligible"] is True
    assert "database_json" not in payload
    assert "manifest_json" not in payload

    listed = db_client.get("/api/v1/catalog/imports")
    assert listed.status_code == 200
    assert len(listed.json()) >= 1
    assert listed.json()[0]["id"] == payload["id"]
    assert "created" not in listed.json()[0]

    detail = db_client.get(f"/api/v1/catalog/imports/{payload['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["archive_sha256"] == payload["archive_sha256"]
    assert "tables_json" not in body
    assert "created" not in body


def test_no_update_or_delete_import_routes(db_client: TestClient) -> None:
    assert db_client.put("/api/v1/catalog/imports/1").status_code in {405, 404}
    assert db_client.patch("/api/v1/catalog/imports/1").status_code in {405, 404}
    assert db_client.delete("/api/v1/catalog/imports/1").status_code in {405, 404}


def test_readiness_filter_invalid_returns_422(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/catalog/imports?package_readiness=INVALID")
    assert response.status_code == 422


def test_secret_field_import_does_not_create_row(db_session: Session) -> None:
    files = build_core_documents()
    database = json.loads(files["database.json"])
    database["password"] = "nope"
    files["database.json"] = json.dumps(database, separators=(",", ":")).encode("utf-8")
    archive = build_package_zip(files=files)
    before = _count_rows(db_session)
    with pytest.raises(CatalogPackageValidationError) as exc_info:
        import_catalog_package_bytes(archive, db_session)
    assert exc_info.value.code == CatalogPackageErrorCode.FORBIDDEN_SECRET_FIELD
    assert _count_rows(db_session) == before


def test_persisted_generated_at_matches_validated(db_session: Session) -> None:
    archive = build_package_zip()
    validated = validate_catalog_package_bytes(archive)
    revision, _ = import_catalog_package_bytes(archive, db_session)
    assert revision.generated_at == validated.generated_at


def test_stored_json_documents_match_validation(db_session: Session) -> None:
    archive = build_package_zip()
    validated = validate_catalog_package_bytes(archive)
    revision, _ = import_catalog_package_bytes(archive, db_session)
    assert revision.latest_run_json == validated.parsed_documents["analysis/latest_run.json"]
    assert revision.schema_snapshot_json == validated.parsed_documents["analysis/schema_snapshot.json"]
    assert revision.preflight_json == validated.parsed_documents["validation/preflight.json"]
    assert revision.latest_diff_json == validated.parsed_documents["diff/latest.json"]
    assert revision.erd_json == validated.parsed_documents["erd.json"]
    assert revision.categories_json == validated.parsed_documents["categories.json"]
    assert revision.managed_file_digests_json == validated.managed_file_digests
