"""Active Catalog management integration tests."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import CatalogActivationErrorCode
from app.adapters.db.session import get_session_factory
from app.models.catalog_active import CatalogActivationEvent, CatalogActiveRevision
from app.models.catalog_import import CatalogImportRevision
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from tests.catalog_package_fixtures import DEFAULT_SOURCE, build_package_zip

pytestmark = pytest.mark.integration

SOURCE_A = dict(DEFAULT_SOURCE)
SOURCE_B = {
    "source_name": "oracle_demis_other",
    "db_type": "oracle",
    "database_name": "FREEPDB1",
    "default_schema": "DEMIS_OTHER",
}


def _import_ready(
    session: Session,
    *,
    source: dict | None = None,
    fingerprint: str = "fp-active-001",
) -> CatalogImportRevision:
    archive = build_package_zip(
        package_readiness="READY",
        source=source or SOURCE_A,
        fingerprint=fingerprint,
    )
    revision, created = import_catalog_package_bytes(archive, session)
    assert created is True
    session.flush()
    return revision


def _count_events(session: Session, source_name: str | None = None) -> int:
    stmt = select(func.count()).select_from(CatalogActivationEvent)
    if source_name is not None:
        stmt = stmt.where(CatalogActivationEvent.source_name == source_name)
    return int(session.scalar(stmt) or 0)


def _count_pointers(session: Session) -> int:
    return int(session.scalar(select(func.count()).select_from(CatalogActiveRevision)) or 0)


def test_ready_first_activation_creates_pointer_and_event(
    db_session: Session, db_client: TestClient
) -> None:
    revision = _import_ready(db_session, fingerprint="fp-act-1")
    db_session.commit()

    response = db_client.post(f"/api/v1/catalog/imports/{revision.id}/activate")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_name"] == SOURCE_A["source_name"]
    assert payload["active_revision_id"] == revision.id
    assert payload["previous_revision_id"] is None
    assert payload["schema_fingerprint"] == "fp-act-1"
    assert payload["package_readiness"] == "READY"
    assert payload["changed"] is True
    assert payload["activated_at"]

    assert _count_pointers(db_session) == 1
    assert _count_events(db_session, SOURCE_A["source_name"]) == 1


def test_warning_activation_rejected(db_session: Session, db_client: TestClient) -> None:
    archive = build_package_zip(package_readiness="WARNING", fingerprint="fp-warn-1")
    revision, _ = import_catalog_package_bytes(archive, db_session)
    db_session.commit()

    response = db_client.post(f"/api/v1/catalog/imports/{revision.id}/activate")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
    assert _count_events(db_session) == 0
    assert _count_pointers(db_session) == 0


def test_blocked_activation_rejected(db_session: Session, db_client: TestClient) -> None:
    archive = build_package_zip(package_readiness="BLOCKED", fingerprint="fp-block-1")
    revision, _ = import_catalog_package_bytes(archive, db_session)
    db_session.commit()

    response = db_client.post(f"/api/v1/catalog/imports/{revision.id}/activate")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE


def test_nonexistent_revision_activation_404(db_client: TestClient) -> None:
    response = db_client.post("/api/v1/catalog/imports/999999/activate")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == CatalogActivationErrorCode.IMPORT_NOT_FOUND


def test_idempotent_reactivation_no_new_event(
    db_session: Session, db_client: TestClient
) -> None:
    revision = _import_ready(db_session, fingerprint="fp-idem-1")
    db_session.commit()

    first = db_client.post(f"/api/v1/catalog/imports/{revision.id}/activate")
    assert first.status_code == 200
    assert first.json()["changed"] is True
    events_before = _count_events(db_session)

    second = db_client.post(f"/api/v1/catalog/imports/{revision.id}/activate")
    assert second.status_code == 200
    payload = second.json()
    assert payload["changed"] is False
    assert payload["active_revision_id"] == revision.id
    assert _count_events(db_session) == events_before
    assert _count_pointers(db_session) == 1


def test_revision_switch_updates_pointer_keeps_old_row(
    db_session: Session, db_client: TestClient
) -> None:
    rev1 = _import_ready(db_session, fingerprint="fp-sw-1")
    rev2 = _import_ready(db_session, fingerprint="fp-sw-2")
    db_session.commit()

    r1 = db_client.post(f"/api/v1/catalog/imports/{rev1.id}/activate")
    assert r1.status_code == 200
    assert r1.json()["previous_revision_id"] is None

    r2 = db_client.post(f"/api/v1/catalog/imports/{rev2.id}/activate")
    assert r2.status_code == 200
    payload = r2.json()
    assert payload["changed"] is True
    assert payload["active_revision_id"] == rev2.id
    assert payload["previous_revision_id"] == rev1.id

    # Old import revision row remains unchanged.
    db_session.expire_all()
    kept = db_session.get(CatalogImportRevision, rev1.id)
    assert kept is not None
    assert kept.schema_fingerprint == "fp-sw-1"
    assert kept.package_readiness == "READY"

    assert _count_pointers(db_session) == 1
    assert _count_events(db_session, SOURCE_A["source_name"]) == 2

    active = db_client.get(f"/api/v1/catalog/active/{SOURCE_A['source_name']}")
    assert active.status_code == 200
    assert active.json()["revision_id"] == rev2.id


def test_cross_source_isolation(db_session: Session, db_client: TestClient) -> None:
    rev_a = _import_ready(db_session, source=SOURCE_A, fingerprint="fp-iso-a")
    rev_b = _import_ready(db_session, source=SOURCE_B, fingerprint="fp-iso-b")
    db_session.commit()

    assert db_client.post(f"/api/v1/catalog/imports/{rev_a.id}/activate").status_code == 200
    assert db_client.post(f"/api/v1/catalog/imports/{rev_b.id}/activate").status_code == 200

    list_resp = db_client.get("/api/v1/catalog/active")
    assert list_resp.status_code == 200
    by_source = {row["source_name"]: row["revision_id"] for row in list_resp.json()}
    assert by_source[SOURCE_A["source_name"]] == rev_a.id
    assert by_source[SOURCE_B["source_name"]] == rev_b.id

    # Switch A must not affect B.
    rev_a2 = _import_ready(db_session, source=SOURCE_A, fingerprint="fp-iso-a2")
    db_session.commit()
    switch = db_client.post(f"/api/v1/catalog/imports/{rev_a2.id}/activate")
    assert switch.status_code == 200
    assert switch.json()["active_revision_id"] == rev_a2.id

    still_b = db_client.get(f"/api/v1/catalog/active/{SOURCE_B['source_name']}")
    assert still_b.json()["revision_id"] == rev_b.id


def test_get_active_list_and_missing_source(
    db_session: Session, db_client: TestClient
) -> None:
    revision = _import_ready(db_session, fingerprint="fp-list-1")
    db_session.commit()
    db_client.post(f"/api/v1/catalog/imports/{revision.id}/activate")

    listed = db_client.get("/api/v1/catalog/active")
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["revision_id"] == revision.id
    assert "manifest_json" not in listed.json()[0]

    missing = db_client.get("/api/v1/catalog/active/no_such_source")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == CatalogActivationErrorCode.ACTIVE_REVISION_NOT_FOUND


def test_activation_history_order_and_filter(
    db_session: Session, db_client: TestClient
) -> None:
    rev_a1 = _import_ready(db_session, source=SOURCE_A, fingerprint="fp-hist-a1")
    rev_a2 = _import_ready(db_session, source=SOURCE_A, fingerprint="fp-hist-a2")
    rev_b = _import_ready(db_session, source=SOURCE_B, fingerprint="fp-hist-b")
    db_session.commit()

    db_client.post(f"/api/v1/catalog/imports/{rev_a1.id}/activate")
    db_client.post(f"/api/v1/catalog/imports/{rev_a2.id}/activate")
    db_client.post(f"/api/v1/catalog/imports/{rev_b.id}/activate")

    all_events = db_client.get("/api/v1/catalog/activations")
    assert all_events.status_code == 200
    rows = all_events.json()
    assert len(rows) == 3
    # Newest first.
    assert rows[0]["activated_revision_id"] == rev_b.id
    assert rows[1]["activated_revision_id"] == rev_a2.id
    assert rows[1]["previous_revision_id"] == rev_a1.id
    assert rows[2]["activated_revision_id"] == rev_a1.id
    assert rows[2]["previous_revision_id"] is None

    filtered = db_client.get(
        "/api/v1/catalog/activations",
        params={"source_name": SOURCE_A["source_name"]},
    )
    assert len(filtered.json()) == 2
    assert all(row["source_name"] == SOURCE_A["source_name"] for row in filtered.json())


def test_no_update_delete_activation_audit_api(db_client: TestClient) -> None:
    assert db_client.put("/api/v1/catalog/activations").status_code == 405
    assert db_client.patch("/api/v1/catalog/activations").status_code == 405
    assert db_client.delete("/api/v1/catalog/activations").status_code == 405
    assert db_client.post("/api/v1/catalog/activations").status_code == 405
    assert db_client.put("/api/v1/catalog/active/oracle_demis_mock").status_code == 405
    assert db_client.delete("/api/v1/catalog/active/oracle_demis_mock").status_code == 405
    assert db_client.patch("/api/v1/catalog/active/oracle_demis_mock").status_code == 405


def test_activation_does_not_mutate_import_revision(
    db_session: Session, db_client: TestClient
) -> None:
    revision = _import_ready(db_session, fingerprint="fp-immut-1")
    db_session.commit()
    before = {
        "fingerprint": revision.schema_fingerprint,
        "readiness": revision.package_readiness,
        "validation_status": revision.validation_status,
        "archive_sha256": revision.archive_sha256,
        "imported_at": revision.imported_at,
    }

    assert db_client.post(f"/api/v1/catalog/imports/{revision.id}/activate").status_code == 200
    db_session.expire_all()
    after = db_session.get(CatalogImportRevision, revision.id)
    assert after is not None
    assert after.schema_fingerprint == before["fingerprint"]
    assert after.package_readiness == before["readiness"]
    assert after.validation_status == before["validation_status"]
    assert after.archive_sha256 == before["archive_sha256"]
    assert after.imported_at == before["imported_at"]


def test_warning_blocked_still_visible_in_history(
    db_session: Session, db_client: TestClient
) -> None:
    warn_archive = build_package_zip(package_readiness="WARNING", fingerprint="fp-vis-w")
    block_archive = build_package_zip(package_readiness="BLOCKED", fingerprint="fp-vis-b")
    warn, _ = import_catalog_package_bytes(warn_archive, db_session)
    block, _ = import_catalog_package_bytes(block_archive, db_session)
    db_session.commit()

    listed = db_client.get("/api/v1/catalog/imports")
    ids = {row["id"] for row in listed.json()}
    assert warn.id in ids
    assert block.id in ids

    detail_w = db_client.get(f"/api/v1/catalog/imports/{warn.id}")
    detail_b = db_client.get(f"/api/v1/catalog/imports/{block.id}")
    assert detail_w.status_code == 200
    assert detail_b.status_code == 200
    assert detail_w.json()["package_readiness"] == "WARNING"
    assert detail_b.json()["package_readiness"] == "BLOCKED"
    assert detail_w.json()["activation_eligible"] is False
    assert detail_b.json()["activation_eligible"] is False


def test_concurrent_activation_single_pointer(
    db_session: Session, test_settings_env: dict[str, str]
) -> None:
    """Two READY revisions racing activate for the same source leave one pointer."""
    rev1 = _import_ready(db_session, fingerprint="fp-race-1")
    rev2 = _import_ready(db_session, fingerprint="fp-race-2")
    db_session.commit()
    ids = (rev1.id, rev2.id)

    errors: list[BaseException] = []
    results: list[bool] = []
    barrier = threading.Barrier(2)

    def _worker(revision_id: int) -> None:
        session = get_session_factory()()
        try:
            barrier.wait(timeout=5)
            result = activate_catalog_revision(session, revision_id)
            session.commit()
            results.append(result.changed)
        except BaseException as exc:  # noqa: BLE001 - collect for assertion
            session.rollback()
            errors.append(exc)
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_worker, rid) for rid in ids]
        for future in futures:
            future.result(timeout=10)

    assert not errors
    assert len(results) == 2

    db_session.expire_all()
    pointers = list(db_session.scalars(select(CatalogActiveRevision)).all())
    assert len(pointers) == 1
    assert pointers[0].source_name == SOURCE_A["source_name"]
    assert pointers[0].catalog_import_revision_id in ids

    events = list(
        db_session.scalars(
            select(CatalogActivationEvent).where(
                CatalogActivationEvent.source_name == SOURCE_A["source_name"]
            )
        ).all()
    )
    # At least one real change; idempotent path may skip a second event.
    assert 1 <= len(events) <= 2
    assert all(e.activated_revision_id in ids for e in events)


def test_invalid_validation_status_not_activatable(db_session: Session) -> None:
    revision = _import_ready(db_session, fingerprint="fp-bad-status")
    db_session.execute(
        text(
            "UPDATE catalog_import_revisions SET validation_status = 'INVALID' WHERE id = :id"
        ),
        {"id": revision.id},
    )
    db_session.commit()
    db_session.expire_all()

    with pytest.raises(Exception) as exc_info:
        activate_catalog_revision(db_session, revision.id)
    assert exc_info.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE  # type: ignore[attr-defined]
