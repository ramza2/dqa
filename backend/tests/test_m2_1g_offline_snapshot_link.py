"""M2-1G internal Snapshot bridge; pure fake-session tests, no Oracle/PG."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.services import offline_snapshot_link as bridge
from app.services.dba_metadata_offline import SOURCE
from app.services.offline_snapshot_link import OfflineSnapshotLinkError
from app.services.schema_snapshot_review import SnapshotReviewError
from tests.test_m2_1d_offline_metadata_export import encode, envelope
from tests.test_m2_1e_offline_provenance import fixture_claim, raw_claim
from tests.test_m2_1f_offline_review_draft import review_fixture
from tests.test_schema_snapshot_history import _base, _capture
from tests.test_schema_snapshot_review import _history

NOW = datetime(2026, 10, 27, 8, 0, tzinfo=timezone.utc)


def _files():
    metadata = encode(envelope(_base()))
    claim = raw_claim(fixture_claim(metadata))
    draft = encode(review_fixture(metadata, claim))
    return metadata, claim, draft


def _db(monkeypatch, *, second=False, changed=False):
    db = _history(monkeypatch, with_second=second, changed=changed)

    def get(_session, revision_id, *, source_name):
        if source_name != SOURCE:
            return None
        return next((r for r in db.rows if r.id == revision_id), None)

    def list_rows(_session, *, source_name, limit=100, offset=0):
        if source_name != SOURCE:
            return []
        return list(reversed(db.rows))[offset:offset + limit]

    monkeypatch.setattr(bridge, "get_snapshot_revision", get)
    monkeypatch.setattr(bridge, "list_snapshot_revisions", list_rows)
    return db


def _preview(db, *, revision=1, source=SOURCE, files=None):
    raw, claim, draft = files or _files()
    return bridge.preview_offline_snapshot_link(
        db, source_name=source, revision_id=revision,
        raw_metadata=raw, raw_claim=claim, raw_review_draft=draft, now=NOW,
    )


def _untrusted(result):
    assert result.issuer_authenticated is False
    assert result.review_actor_authenticated is False
    assert result.independent_preflight_verified is False
    assert result.site_approval_verified is False
    assert result.catalog_package_readiness == "WARNING"
    assert result.catalog_ready is False
    assert result.activation_eligible is False
    assert result.stored_snapshot_verified is True


def test_latest_matching_snapshot_remains_untrusted_and_review_required(monkeypatch):
    db = _db(monkeypatch)
    before = deepcopy(db.rows[0].snapshot_json)
    result = _preview(db)
    assert result.link_status == "STRUCTURAL_MATCH_UNTRUSTED"
    assert result.identical is True and result.total_changes == 0
    assert result.review_draft_status == "ACKNOWLEDGED_UNVERIFIED"
    assert result.stored_review_status == "REVIEW_REQUIRED"
    assert result.latest_revision_id == 1
    _untrusted(result)
    assert len(db.rows) == 1
    assert db.rows[0].snapshot_json == before


def test_latest_different_structure_reports_counts_only(monkeypatch):
    db = _db(monkeypatch, second=True, changed=True)
    result = _preview(db, revision=2)
    assert result.link_status == "STRUCTURAL_DIFFERENCE_UNTRUSTED"
    assert result.identical is False
    assert result.total_changes == 1
    assert result.latest_revision_id == 2
    assert "changed private value" not in str(result)
    _untrusted(result)
    assert len(db.rows) == 2


def test_superseded_snapshot_never_matches_even_if_same(monkeypatch):
    db = _db(monkeypatch, second=True)
    result = _preview(db, revision=1)
    assert result.link_status == "SUPERSEDED"
    assert result.identical is None and result.total_changes is None
    assert result.latest_revision_id == 2
    _untrusted(result)


@pytest.mark.parametrize("source,revision", [
    ("live_demis", 1), (SOURCE, 0), (SOURCE, True), (SOURCE, "1"),
])
def test_invalid_target_fails_before_read(monkeypatch, source, revision):
    db = _db(monkeypatch)
    with pytest.raises(OfflineSnapshotLinkError, match="INVALID_SNAPSHOT_LINK_TARGET"):
        _preview(db, revision=revision, source=source)


@pytest.mark.parametrize("source,revision", [(SOURCE, 999)])
def test_missing_revision_fails_closed(monkeypatch, source, revision):
    db = _db(monkeypatch)
    with pytest.raises(OfflineSnapshotLinkError, match="SNAPSHOT_REVISION_NOT_FOUND"):
        _preview(db, source=source, revision=revision)


@pytest.mark.parametrize("corrupt", ["hash", "counts", "diff", "target", "payload"])
def test_corrupt_stored_snapshot_rejected(monkeypatch, corrupt):
    db = _db(monkeypatch)
    row = db.rows[0]
    if corrupt == "hash":
        row.schema_fingerprint = "f" * 64
    elif corrupt == "counts":
        row.counts_json["columns"] = 88
    elif corrupt == "diff":
        row.diff_summary_json["status"] = "COMPARED"
    elif corrupt == "target":
        row.schema_name = "SENSITIVE_NAME"
    elif corrupt == "payload":
        row.snapshot_json["columns"][0]["column_comment"] = "PATIENT_PRIVATE_COMMENT"

    with pytest.raises(OfflineSnapshotLinkError, match="SNAPSHOT_LINK_UNVERIFIABLE") as caught:
        _preview(db)
    assert "SENSITIVE_NAME" not in str(caught.value)
    assert "PATIENT_PRIVATE_COMMENT" not in str(caught.value)


def test_untrusted_claim_tampering_rejected_before_snapshot_lookup(monkeypatch):
    db = _db(monkeypatch)
    raw, claim, draft = _files()
    modified = raw_claim({**fixture_claim(raw), "schema_fingerprint": "a" * 64})
    with pytest.raises(OfflineSnapshotLinkError, match="INVALID_OFFLINE_REVIEW_BUNDLE"):
        _preview(db, files=(raw, modified, draft))


def test_untrusted_review_tampering_rejected(monkeypatch):
    db = _db(monkeypatch)
    raw, claim, draft = _files()
    modified = encode({**review_fixture(raw, claim), "approved": True})
    with pytest.raises(OfflineSnapshotLinkError, match="INVALID_OFFLINE_REVIEW_BUNDLE"):
        _preview(db, files=(raw, claim, modified))


def test_new_capture_during_comparison_blocks_positive_match(monkeypatch):
    db = _db(monkeypatch)
    original_compare = bridge.compare_schema_snapshots

    def compare_then_capture(a, b):
        outcome = original_compare(a, b)
        new_row = _capture(db, expected=1).revision
        new_row.captured_at = db.rows[0].captured_at
        return outcome

    monkeypatch.setattr(bridge, "compare_schema_snapshots", compare_then_capture)
    result = _preview(db)
    assert result.link_status == "SUPERSEDED"
    assert result.latest_revision_id == 2
    assert result.identical is None
    _untrusted(result)


def test_stored_database_read_failure_never_exposes_exception_text(monkeypatch):
    db = _db(monkeypatch)

    def fail(*_args, **_kwargs):
        raise RuntimeError("SECRET_DB_PASSWORD")

    monkeypatch.setattr(bridge, "get_snapshot_revision", fail)
    with pytest.raises(OfflineSnapshotLinkError) as caught:
        _preview(db)
    assert str(caught.value) == "SNAPSHOT_LINK_UNVERIFIABLE"
    assert "SECRET_DB_PASSWORD" not in str(caught.value)


def test_no_http_catalog_mutation_or_external_approval_hooks():
    # Guard against accidental service-level imports of mutating gateways.
    import inspect
    src = inspect.getsource(bridge)
    assert "capture_snapshot_revision(" not in src
    assert "record_review_event(" not in src
    assert ".commit(" not in src
    assert "activate_catalog" not in src
    assert "create_engine(" not in src
