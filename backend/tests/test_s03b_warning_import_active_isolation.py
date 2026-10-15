"""S-03-B: real Package v2 + Catalog HTTP/services with synthetic persistence.

Uses existing ZIP builder/validator, import service, activation guard and query
reader, but NEVER the DQA PostgreSQL, Oracle or clinical data. In particular,
do not use the integration db_session fixture: it TRUNCATEs catalog tables.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.adapters.db.deps import get_db_session
from app.adapters.catalog.activation_errors import CatalogActivationErrorCode
from app.adapters.catalog.query_errors import CatalogQueryError
from app.services import catalog_active, catalog_package_import, catalog_query
from app.services import schema_snapshot_review as snapshot_review
from tests.catalog_package_fixtures import DEFAULT_SOURCE, build_package_zip
from tests.test_schema_snapshot_review import _history

SOURCE = DEFAULT_SOURCE["source_name"]
IMPORT_URL = "/api/v1/catalog/packages/import"
VALIDATE_URL = "/api/v1/catalog/packages/validate"


@dataclass
class SyntheticCatalogStore:
    imports: dict[int, object] = field(default_factory=dict)
    active: dict[str, object] = field(default_factory=dict)
    events: list[object] = field(default_factory=list)

    def flush(self):
        """No real DB; pointer changes are synchronous."""
        pass


class SyntheticImportRepository:
    def __init__(self, store):
        self.store = store

    def get_by_archive_sha256(self, digest):
        return next(
            (r for r in self.store.imports.values() if r.archive_sha256 == digest),
            None,
        )

    def get_by_id(self, revision_id):
        return self.store.imports.get(revision_id)

    def add(self, revision):
        revision.id = len(self.store.imports) + 1
        self.store.imports[revision.id] = revision
        return revision

    def list_revisions(self, *, source_name=None, package_readiness=None, limit=100, offset=0):
        rows = [
            row for row in self.store.imports.values()
            if (source_name is None or row.source_name == source_name)
            and (package_readiness is None or row.package_readiness == package_readiness)
        ]
        return sorted(rows, key=lambda row: row.id, reverse=True)[offset:offset + limit]


class SyntheticActiveRepository:
    def __init__(self, store):
        self.store = store

    def get_active_by_source_name(self, source_name, *, for_update=False):
        return self.store.active.get(source_name)

    def list_active(self):
        return list(self.store.active.values())

    def add_active(self, pointer):
        pointer.id = len(self.store.active) + 1
        self.store.active[pointer.source_name] = pointer
        return pointer

    def add_event(self, event):
        event.id = len(self.store.events) + 1
        self.store.events.append(event)
        return event

    def list_events(self, *, source_name=None, limit=100, offset=0):
        rows = [
            event for event in self.store.events
            if source_name is None or event.source_name == source_name
        ]
        return list(reversed(rows))[offset:offset + limit]


@pytest.fixture()
def synthetic_catalog(client, monkeypatch):
    store = SyntheticCatalogStore()

    # Patch only repositories. The real routes, ZIP validation, import,
    # activation policy and Catalog query services all execute unchanged.
    for module in (catalog_package_import, catalog_active, catalog_query):
        monkeypatch.setattr(module, "CatalogImportRepository", SyntheticImportRepository)
    for module in (catalog_active, catalog_query):
        monkeypatch.setattr(module, "CatalogActiveRepository", SyntheticActiveRepository)
    client.app.dependency_overrides[get_db_session] = lambda: store
    try:
        yield client, store
    finally:
        client.app.dependency_overrides.pop(get_db_session, None)


def _import(client, archive):
    return client.post(
        IMPORT_URL,
        files={"file": ("synthetic-catalog.zip", archive, "application/zip")},
    )


def _warning_from_latest_snapshot(monkeypatch):
    history = _history(monkeypatch)
    candidate = snapshot_review.build_latest_snapshot_warning_candidate(
        history, source_name=SOURCE, revision_id=1,
    )
    assert candidate.package_readiness == "WARNING"
    assert candidate.preflight_status == "NOT_VERIFIED"
    assert candidate.activation_eligible is False
    return candidate, history


def test_warning_snapshot_zip_import_and_activation_rejection_preserve_active_and_query(
    synthetic_catalog, monkeypatch,
):
    client, store = synthetic_catalog

    # Establish an already active, unrelated READY Catalog revision.
    ready_zip = build_package_zip(package_readiness="READY", fingerprint="synthetic-active")
    ready = _import(client, ready_zip)
    assert ready.status_code == 200, ready.text
    ready_id = ready.json()["id"]
    assert ready.json()["package_readiness"] == "READY"

    activated = client.post(f"/api/v1/catalog/imports/{ready_id}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["changed"] is True

    before_active = client.get(f"/api/v1/catalog/active/{SOURCE}")
    assert before_active.status_code == 200
    before_tables = catalog_query.list_tables(store, SOURCE)[1]
    before_names = [item.name for item in before_tables.items]
    before_events = list(store.events)
    assert before_names

    candidate, history = _warning_from_latest_snapshot(monkeypatch)
    validated = client.post(
        VALIDATE_URL,
        files={"file": ("warning.zip", candidate.archive_bytes, "application/zip")},
    )
    assert validated.status_code == 200, validated.text
    assert validated.json()["package_readiness"] == "WARNING"
    assert validated.json()["activation_eligible"] is False

    imported = _import(client, candidate.archive_bytes)
    assert imported.status_code == 200, imported.text
    warning_id = imported.json()["id"]
    assert warning_id != ready_id
    assert imported.json()["created"] is True
    assert imported.json()["package_readiness"] == "WARNING"
    assert imported.json()["activation_eligible"] is False
    assert imported.json()["schema_fingerprint"] == candidate.schema_fingerprint

    repeated = _import(client, candidate.archive_bytes)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["created"] is False
    assert repeated.json()["id"] == warning_id
    assert len(store.imports) == 2

    forbidden = client.post(f"/api/v1/catalog/imports/{warning_id}/activate")
    assert forbidden.status_code == 409
    assert forbidden.json()["detail"]["code"] == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
    assert client.get(f"/api/v1/catalog/active/{SOURCE}").json() == before_active.json()
    assert [item.name for item in catalog_query.list_tables(store, SOURCE)[1].items] == before_names
    assert store.active[SOURCE].catalog_import_revision_id == ready_id
    assert len(store.events) == len(before_events) == 1
    assert store.events[0] is before_events[0]
    assert len(history.rows) == 1  # Inspector Snapshot history was untouched

    warning_detail = client.get(f"/api/v1/catalog/imports/{warning_id}")
    assert warning_detail.status_code == 200
    assert warning_detail.json()["package_readiness"] == "WARNING"
    assert warning_detail.json()["activation_eligible"] is False


def test_warning_import_without_active_pointer_never_implicitly_activates(
    synthetic_catalog, monkeypatch,
):
    client, store = synthetic_catalog
    candidate, _ = _warning_from_latest_snapshot(monkeypatch)
    imported = _import(client, candidate.archive_bytes)
    assert imported.status_code == 200, imported.text
    warning_id = imported.json()["id"]
    assert imported.json()["activation_eligible"] is False
    assert store.active == {}
    assert store.events == []

    denied = client.post(f"/api/v1/catalog/imports/{warning_id}/activate")
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
    assert client.get(f"/api/v1/catalog/active/{SOURCE}").status_code == 404
    with pytest.raises(CatalogQueryError):
        catalog_query.list_tables(store, SOURCE)
    assert store.active == {}
    assert store.events == []


def test_malformed_followup_import_preserves_ready_pointer_and_catalog_query(
    synthetic_catalog,
):
    client, store = synthetic_catalog
    ready = _import(
        client, build_package_zip(package_readiness="READY", fingerprint="initial-ready"),
    )
    assert ready.status_code == 200, ready.text
    ready_id = ready.json()["id"]
    assert client.post(f"/api/v1/catalog/imports/{ready_id}/activate").status_code == 200

    initial = catalog_query.list_tables(store, SOURCE)[1]
    active_before = client.get(f"/api/v1/catalog/active/{SOURCE}").json()
    assert initial.total >= 1

    invalid = _import(client, b"not a real ZIP; synthetic-only")
    assert invalid.status_code == 400
    assert len(store.imports) == 1
    assert len(store.events) == 1
    assert client.get(f"/api/v1/catalog/active/{SOURCE}").json() == active_before
    after = catalog_query.list_tables(store, SOURCE)[1]
    assert [t.name for t in after.items] == [t.name for t in initial.items]
