"""S-04-C-2B-2B stored Snapshot -> offline contract, synthetic only.

No live DQA PostgreSQL, Oracle connection, HTTP route, or Catalog mutation.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.services import schema_preflight_snapshot as bridge
from app.services.schema_snapshot_review import SnapshotReviewError
from tests.mock_schema_preflight_provider import SyntheticEvidenceProvider
from tests.test_schema_snapshot_history import _base, _capture
from tests.test_schema_snapshot_review import _history

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
SOURCE = "oracle_demis_mock"


def _mock_history(monkeypatch, *, with_second=False, changed=False):
    db = _history(monkeypatch, with_second=with_second, changed=changed)

    def get(_session, revision_id, *, source_name):
        if source_name != SOURCE:
            return None
        return next((row for row in db.rows if row.id == revision_id), None)

    def list_rows(_session, *, source_name, limit=100, offset=0):
        if source_name != SOURCE:
            return []
        return list(reversed(db.rows))[offset:offset + limit]

    monkeypatch.setattr(bridge, "get_snapshot_revision", get)
    monkeypatch.setattr(bridge, "list_snapshot_revisions", list_rows)
    return db


def _fake():
    return SyntheticEvidenceProvider(independently_constructed_mock_snapshot=_base())


def _run(db, *, provider=None, source=SOURCE, revision=1):
    return bridge.check_stored_snapshot_preflight_contract(
        db, source_name=source, revision_id=revision,
        provider=provider, now=NOW,
    )


def _assert_blocked(result):
    assert result.preflight_status == "NOT_VERIFIED"
    assert result.independently_authenticated is False
    assert result.replay_protected is False
    assert result.revocation_checked is False
    assert result.catalog_ready is False
    assert result.activation_eligible is False


def test_default_missing_provider_from_persisted_context(monkeypatch):
    db = _mock_history(monkeypatch)
    result = _run(db)
    assert result.reason_code == "NO_TRUSTED_PROVIDER"
    assert not result.structural_match
    _assert_blocked(result)
    assert len(db.rows) == 1
    assert db.lock_calls == ["dqa:snapshot:oracle_demis_mock"]


def test_separately_constructed_mock_match_still_not_dba_approved(monkeypatch):
    db = _mock_history(monkeypatch)
    provider = _fake()
    result = _run(db, provider=provider)
    assert provider.calls == 1
    assert result.reason_code == "STRUCTURAL_MATCH_ONLY"
    assert result.structural_match
    _assert_blocked(result)
    assert len(db.rows) == 1


def test_latest_identical_second_revision_does_not_auto_approve(monkeypatch):
    db = _mock_history(monkeypatch, with_second=True)
    result = _run(db, provider=_fake(), revision=2)
    assert result.reason_code == "STRUCTURAL_MATCH_ONLY"
    _assert_blocked(result)
    assert len(db.rows) == 2


def test_latest_modified_second_revision_mismatches_mock(monkeypatch):
    db = _mock_history(monkeypatch, with_second=True, changed=True)
    result = _run(db, provider=_fake(), revision=2)
    assert result.reason_code == "FINGERPRINT_MISMATCH"
    assert not result.structural_match
    _assert_blocked(result)


def test_superseded_revision_skips_provider(monkeypatch):
    db = _mock_history(monkeypatch, with_second=True)
    provider = _fake()
    result = _run(db, provider=provider, revision=1)
    assert result.reason_code == "SUPERSEDED_SNAPSHOT"
    assert provider.calls == 0
    _assert_blocked(result)


@pytest.mark.parametrize("source,revision", [
    ("another_source", 1),
    (SOURCE, 999),
])
def test_unknown_or_cross_source_revision_is_not_found(monkeypatch, source, revision):
    db = _mock_history(monkeypatch)
    provider = _fake()
    with pytest.raises(SnapshotReviewError, match="SNAPSHOT_REVISION_NOT_FOUND"):
        _run(db, provider=provider, source=source, revision=revision)
    assert provider.calls == 0


@pytest.mark.parametrize("corrupt", ["fp", "target", "counts", "diff", "snapshot"])
def test_tampered_stored_snapshot_fails_before_provider(monkeypatch, corrupt):
    db = _mock_history(monkeypatch)
    row = db.rows[0]
    if corrupt == "fp":
        row.schema_fingerprint = "0" * 64
    elif corrupt == "target":
        row.database_name = "SECRET_DB"
    elif corrupt == "counts":
        row.counts_json["tables"] = 100
    elif corrupt == "diff":
        row.diff_summary_json["status"] = "COMPARED"
    elif corrupt == "snapshot":
        row.snapshot_json["tables"][0]["table_comment"] = "SENSITIVE_COMMENT"

    provider = _fake()
    with pytest.raises(SnapshotReviewError) as caught:
        _run(db, provider=provider)
    assert caught.value.code == "SNAPSHOT_REVIEW_UNVERIFIABLE"
    assert "SENSITIVE_COMMENT" not in str(caught.value)
    assert "SECRET_DB" not in str(caught.value)
    assert provider.calls == 0


def test_provider_failure_never_leaks_data(monkeypatch):
    db = _mock_history(monkeypatch)
    provider = _fake()
    provider.fail = True
    result = _run(db, provider=provider)
    assert result.reason_code == "EVIDENCE_UNAVAILABLE"
    assert "private credential" not in str(result)
    assert provider.calls == 1
    _assert_blocked(result)


def test_new_snapshot_during_provider_evaluation_returns_superseded(monkeypatch):
    db = _mock_history(monkeypatch)
    provider = _fake()
    original_fetch = provider.fetch

    def fetch_then_capture(context):
        evidence = original_fetch(context)
        newer = _capture(db, expected=context.revision_id).revision
        newer.captured_at = db.rows[0].captured_at
        return evidence

    provider.fetch = fetch_then_capture
    result = _run(db, provider=provider)
    assert provider.calls == 1
    assert result.reason_code == "SUPERSEDED_SNAPSHOT"
    assert not result.structural_match
    _assert_blocked(result)
    assert len(db.rows) == 2


def test_latest_fingerprint_change_during_evaluation_fail_closed(monkeypatch):
    db = _mock_history(monkeypatch)
    provider = _fake()
    original_fetch = provider.fetch

    def fetch_then_corrupt(context):
        evidence = original_fetch(context)
        db.rows[0].schema_fingerprint = "b" * 64
        return evidence

    provider.fetch = fetch_then_corrupt
    result = _run(db, provider=provider)
    assert result.reason_code == "SUPERSEDED_SNAPSHOT"
    assert not result.structural_match
    _assert_blocked(result)


def test_storage_read_error_is_sanitized(monkeypatch):
    db = _mock_history(monkeypatch)

    def error(*_args, **_kwargs):
        raise RuntimeError("db-password / patient-row")

    monkeypatch.setattr(bridge, "get_snapshot_revision", error)
    with pytest.raises(SnapshotReviewError) as caught:
        _run(db)
    assert caught.value.code == "SNAPSHOT_PREFLIGHT_CONTEXT_UNAVAILABLE"
    assert "db-password" not in str(caught.value)


def test_provider_has_no_injected_actor_or_approval_scope(monkeypatch):
    db = _mock_history(monkeypatch)

    class InspectionOnlyProvider:
        def fetch(self, context):
            assert context.source_name == SOURCE
            assert context.db_type == "oracle"
            assert not hasattr(context, "approved")
            assert not hasattr(context, "reviewed_by")
            assert not hasattr(context, "credentials")
            assert not hasattr(context, "patient")
            return _fake().fetch(context)

    result = _run(db, provider=InspectionOnlyProvider())
    assert result.reason_code == "STRUCTURAL_MATCH_ONLY"
    _assert_blocked(result)


def test_only_one_source_revision_read_side_no_catalog_side_effect(monkeypatch):
    db = _mock_history(monkeypatch)
    first = deepcopy(db.rows[0].snapshot_json)
    result = _run(db, provider=_fake())
    assert db.rows[0].snapshot_json == first
    assert db.rows[0].id == 1
    assert len(db.rows) == 1
    _assert_blocked(result)
