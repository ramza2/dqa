"""S-03-C: Snapshot/Import revision recovery boundaries, synthetic only.

Use real HTTP routes, v2 validation, Catalog service guards and source-bound
Snapshot builder. Import/Active repositories are in-memory; NO PostgreSQL,
Oracle, DEMIS, migrations or db_session (the latter TRUNCATEs test tables).
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.adapters.catalog.activation_errors import CatalogActivationErrorCode
from app.services import catalog_package_import, catalog_query
from app.services.schema_snapshot_review import (
    SnapshotReviewError,
    build_latest_snapshot_warning_candidate,
)
from app.services.schema_snapshot_history import SnapshotHistoryError
from tests.catalog_package_fixtures import DEFAULT_SOURCE, build_package_zip
from tests.test_s03b_warning_import_active_isolation import (
    SOURCE, SyntheticImportRepository, _import, synthetic_catalog,
)
from tests.test_schema_snapshot_history import _base, _capture
from tests.test_schema_snapshot_review import _history


def _activate_ready(client, *, source=None, fingerprint="ready-original"):
    archive = build_package_zip(
        package_readiness="READY",
        source=source,
        fingerprint=fingerprint,
    )
    imported = _import(client, archive)
    assert imported.status_code == 200, imported.text
    revision_id = imported.json()["id"]
    response = client.post(f"/api/v1/catalog/imports/{revision_id}/activate")
    assert response.status_code == 200, response.text
    return revision_id


def _warning(session, revision_id):
    result = build_latest_snapshot_warning_candidate(
        session, source_name=SOURCE, revision_id=revision_id,
    )
    assert result.package_readiness == "WARNING"
    assert result.preflight_status == "NOT_VERIFIED"
    assert result.activation_eligible is False
    return result


def _assert_active_intact(client, store, revision_id, expected_tables, event_count):
    active = client.get(f"/api/v1/catalog/active/{SOURCE}")
    assert active.status_code == 200, active.text
    assert active.json()["revision_id"] == revision_id
    assert active.json()["package_readiness"] == "READY"
    assert store.active[SOURCE].catalog_import_revision_id == revision_id
    names = [table.name for table in catalog_query.list_tables(store, SOURCE)[1].items]
    assert names == expected_tables
    assert len(store.events) == event_count


def test_changed_snapshot_after_warning_import_retains_previous_active_catalog(
    synthetic_catalog, monkeypatch,
):
    client, store = synthetic_catalog
    ready_id = _activate_ready(client)
    before_tables = [table.name for table in catalog_query.list_tables(store, SOURCE)[1].items]

    history = _history(monkeypatch)
    original = _warning(history, 1)
    first = _import(client, original.archive_bytes)
    assert first.status_code == 200, first.text
    assert first.json()["created"] is True
    first_id = first.json()["id"]
    assert first.json()["activation_eligible"] is False

    updated = deepcopy(_base())
    updated.tables[0] = replace(
        updated.tables[0], table_comment="synthetic changed metadata",
    )
    second_row = _capture(history, snapshot=updated, expected=1).revision
    second_row.captured_at = datetime(2026, 10, 15, tzinfo=timezone.utc)
    assert second_row.id == 2
    assert second_row.previous_revision_id == 1
    assert second_row.schema_fingerprint != history.rows[0].schema_fingerprint

    with pytest.raises(SnapshotReviewError) as caught:
        _warning(history, 1)
    assert caught.value.code == "SNAPSHOT_CANDIDATE_SUPERSEDED"

    revised = _warning(history, 2)
    assert revised.schema_fingerprint != original.schema_fingerprint
    assert revised.archive_sha256 != original.archive_sha256
    second = _import(client, revised.archive_bytes)
    assert second.status_code == 200, second.text
    assert second.json()["created"] is True
    second_id = second.json()["id"]
    assert second_id not in (first_id, ready_id)

    repeated = _import(client, revised.archive_bytes)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created"] is False
    assert repeated.json()["id"] == second_id
    assert len(store.imports) == 3

    for warning_id in (first_id, second_id):
        denied = client.post(f"/api/v1/catalog/imports/{warning_id}/activate")
        assert denied.status_code == 409
        assert denied.json()["detail"]["code"] == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
    _assert_active_intact(client, store, ready_id, before_tables, 1)
    assert len(history.rows) == 2
    assert history.rows[0].id == 1  # append-only baseline


def test_import_repository_failure_before_write_preserves_ready_then_retry_dedup(
    synthetic_catalog, monkeypatch,
):
    client, store = synthetic_catalog
    ready_id = _activate_ready(client)
    baseline = [table.name for table in catalog_query.list_tables(store, SOURCE)[1].items]
    history = _history(monkeypatch)
    artifact = _warning(history, 1)

    class RejectBeforeInsert(SyntheticImportRepository):
        def add(self, _revision):
            raise RuntimeError("synthetic import storage failure - PRIVATE_SECRET")

    # Failure is injected BEFORE a synthetic write. This is not a PostgreSQL
    # transaction rollback test and must never be reported as one.
    monkeypatch.setattr(
        catalog_package_import, "CatalogImportRepository", RejectBeforeInsert,
    )
    with pytest.raises(RuntimeError, match="synthetic import storage failure"):
        _import(client, artifact.archive_bytes)
    _assert_active_intact(client, store, ready_id, baseline, 1)
    assert len(store.imports) == 1
    assert len(history.rows) == 1

    monkeypatch.setattr(
        catalog_package_import, "CatalogImportRepository", SyntheticImportRepository,
    )
    saved = _import(client, artifact.archive_bytes)
    assert saved.status_code == 200, saved.text
    assert saved.json()["created"] is True
    assert saved.json()["package_readiness"] == "WARNING"
    duplicate = _import(client, artifact.archive_bytes)
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["created"] is False
    assert duplicate.json()["id"] == saved.json()["id"]

    rejected = client.post(f"/api/v1/catalog/imports/{saved.json()['id']}/activate")
    assert rejected.status_code == 409
    _assert_active_intact(client, store, ready_id, baseline, 1)


def test_snapshot_capture_replay_and_conflict_do_not_change_import_or_active(
    synthetic_catalog, monkeypatch,
):
    client, store = synthetic_catalog
    ready_id = _activate_ready(client)
    baseline = [table.name for table in catalog_query.list_tables(store, SOURCE)[1].items]

    history = _history(monkeypatch)
    first = history.rows[0]
    request_id = UUID(first.capture_request_id)
    artifact = _warning(history, 1)
    imported = _import(client, artifact.archive_bytes)
    assert imported.status_code == 200
    warning_id = imported.json()["id"]

    replay = _capture(history, request_id=request_id)
    assert replay.created is False
    assert replay.revision.id == first.id
    assert len(history.rows) == 1

    conflicting = deepcopy(_base())
    conflicting.columns[0] = replace(conflicting.columns[0], data_type="NUMBER")
    with pytest.raises(SnapshotHistoryError, match="CAPTURE_REQUEST_REUSED"):
        _capture(history, snapshot=conflicting, request_id=request_id)
    assert len(history.rows) == 1

    same = _warning(history, 1)
    assert same.archive_sha256 == artifact.archive_sha256
    duplicate = _import(client, same.archive_bytes)
    assert duplicate.status_code == 200
    assert duplicate.json()["created"] is False
    assert duplicate.json()["id"] == warning_id
    _assert_active_intact(client, store, ready_id, baseline, 1)


def test_warning_import_for_one_source_leaves_other_source_active_unchanged(
    synthetic_catalog, monkeypatch,
):
    client, store = synthetic_catalog
    other_source = dict(DEFAULT_SOURCE)
    other_source["source_name"] = "oracle_demis_other"
    other_source["default_schema"] = "DEMIS_OTHER"
    other_ready_id = _activate_ready(
        client, source=other_source, fingerprint="other-ready",
    )
    other_before = client.get("/api/v1/catalog/active/oracle_demis_other").json()
    other_tables = [
        table.name for table in catalog_query.list_tables(
            store, "oracle_demis_other",
        )[1].items
    ]

    history = _history(monkeypatch)
    warning = _warning(history, 1)
    imported = _import(client, warning.archive_bytes)
    assert imported.status_code == 200, imported.text
    assert imported.json()["source_name"] == SOURCE
    assert store.active["oracle_demis_other"].catalog_import_revision_id == other_ready_id
    assert client.get("/api/v1/catalog/active/oracle_demis_other").json() == other_before
    assert [t.name for t in catalog_query.list_tables(store, "oracle_demis_other")[1].items] == other_tables
    assert client.get(f"/api/v1/catalog/active/{SOURCE}").status_code == 404
    assert len(store.events) == 1


def test_explicit_switch_back_to_previous_ready_remains_possible_with_warning_history(
    synthetic_catalog, monkeypatch,
):
    client, store = synthetic_catalog
    first_ready = _activate_ready(client, fingerprint="synthetic-ready-a")
    second_ready = _activate_ready(client, fingerprint="synthetic-ready-b")
    assert store.active[SOURCE].catalog_import_revision_id == second_ready
    assert len(store.events) == 2

    history = _history(monkeypatch)
    warning = _warning(history, 1)
    imported = _import(client, warning.archive_bytes)
    assert imported.status_code == 200, imported.text
    rejected = client.post(f"/api/v1/catalog/imports/{imported.json()['id']}/activate")
    assert rejected.status_code == 409

    # Explicit operator action to switch to another already READY revision:
    # NOT automated rollback or permission to promote the WARNING revision.
    restored = client.post(f"/api/v1/catalog/imports/{first_ready}/activate")
    assert restored.status_code == 200, restored.text
    assert restored.json()["changed"] is True
    assert restored.json()["previous_revision_id"] == second_ready
    assert restored.json()["active_revision_id"] == first_ready
    assert len(store.events) == 3
    assert store.events[-1].previous_revision_id == second_ready
    assert store.events[-1].activated_revision_id == first_ready

    warning_row = store.imports[imported.json()["id"]]
    assert warning_row.package_readiness == "WARNING"
    assert store.active[SOURCE].catalog_import_revision_id == first_ready
    assert len(history.rows) == 1
