"""S-04-C-2A offline Snapshot review tests. No Oracle or DQA DB needed."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services import schema_snapshot_review as review
from app.services.schema_snapshot_review import SnapshotReviewError
from tests.test_schema_snapshot_history import FakeSession, _base, _capture

URL = "/api/v1/schema-inspector/snapshots"


def _history(monkeypatch, *, with_second=False, changed=False):
    db = FakeSession()
    first = _capture(db).revision
    first.captured_at = datetime(2026, 10, 14, tzinfo=timezone.utc)
    if with_second:
        newer = deepcopy(_base())
        if changed:
            newer.tables[0] = replace(newer.tables[0], table_comment="changed private value")
        second = _capture(db, snapshot=newer, expected=first.id).revision
        second.captured_at = datetime(2026, 10, 14, tzinfo=timezone.utc)

    def get(_db, revision_id, *, source_name):
        if source_name != "oracle_demis_mock":
            return None
        return next((row for row in db.rows if row.id == revision_id), None)

    def list_rows(_db, *, source_name, limit=100, offset=0):
        if source_name != "oracle_demis_mock":
            return []
        return list(reversed(db.rows))[offset:offset + limit]

    monkeypatch.setattr(review, "get_snapshot_revision", get)
    monkeypatch.setattr(review, "list_snapshot_revisions", list_rows)
    return db


def test_first_revision_no_baseline_never_ready(monkeypatch):
    db = _history(monkeypatch)
    result = review.preview_snapshot_review(
        db, source_name="oracle_demis_mock", revision_id=1,
    )
    assert result.revision_id == 1
    assert result.latest_revision_id == 1
    assert result.is_latest is True
    assert result.diff_status == "NO_BASELINE"
    assert result.identical is None
    assert result.total_changes is None
    assert result.snapshot_verified
    assert result.candidate_package_valid
    assert result.candidate_package_readiness == "WARNING"
    assert result.preflight_status == "NOT_VERIFIED"
    assert result.review_status == "REVIEW_REQUIRED"
    assert result.activation_eligible is False
    assert "INDEPENDENT_PREFLIGHT" in result.required_gates
    assert len(db.rows) == 1


def test_second_identical_still_requires_review_and_independent_preflight(monkeypatch):
    db = _history(monkeypatch, with_second=True)
    result = review.preview_snapshot_review(
        db, source_name="oracle_demis_mock", revision_id=2,
    )
    assert result.diff_status == "COMPARED"
    assert result.identical is True
    assert result.total_changes == 0
    assert result.review_status == "REVIEW_REQUIRED"
    assert result.candidate_package_readiness == "WARNING"
    assert result.preflight_status == "NOT_VERIFIED"
    assert result.activation_eligible is False
    old = review.preview_snapshot_review(
        db, source_name="oracle_demis_mock", revision_id=1,
    )
    assert old.review_status == "SUPERSEDED"
    assert old.is_latest is False
    assert old.latest_revision_id == 2
    assert len(db.rows) == 2


def test_changed_revision_review_verifies_diff_without_values(monkeypatch):
    db = _history(monkeypatch, with_second=True, changed=True)
    result = review.preview_snapshot_review(
        db, source_name="oracle_demis_mock", revision_id=2,
    )
    assert result.total_changes == 1
    assert result.identical is False
    assert result.candidate_package_readiness == "WARNING"
    assert "changed private value" not in str(result)


@pytest.mark.parametrize("damage", ["snapshot", "counts", "diff", "target", "version"])
def test_corrupt_current_revision_fails_closed(monkeypatch, damage):
    db = _history(monkeypatch, with_second=True)
    row = db.rows[-1]
    if damage == "snapshot":
        row.snapshot_json["tables"][0]["table_comment"] = "tampered"
    elif damage == "counts":
        row.counts_json["tables"] = 999
    elif damage == "diff":
        row.diff_summary_json["total_changes"] = 123
    elif damage == "target":
        row.schema_name = "WRONG_SCHEMA"
    elif damage == "version":
        row.snapshot_version = 999
    with pytest.raises(SnapshotReviewError, match="SNAPSHOT_REVIEW_UNVERIFIABLE"):
        review.preview_snapshot_review(
            db, source_name="oracle_demis_mock", revision_id=2,
        )


def test_corrupt_previous_snapshot_fails_closed(monkeypatch):
    db = _history(monkeypatch, with_second=True)
    db.rows[0].snapshot_json["columns"][0]["data_type"] = "private bad data"
    with pytest.raises(SnapshotReviewError, match="SNAPSHOT_REVIEW_UNVERIFIABLE"):
        review.preview_snapshot_review(
            db, source_name="oracle_demis_mock", revision_id=2,
        )


def test_unknown_and_cross_source_are_not_found(monkeypatch):
    db = _history(monkeypatch)
    for source, ident in (("oracle_demis_mock", 123), ("another_source", 1)):
        with pytest.raises(SnapshotReviewError, match="SNAPSHOT_REVISION_NOT_FOUND"):
            review.preview_snapshot_review(
                db, source_name=source, revision_id=ident,
            )


def test_get_review_requires_authentication(unauth_client):
    result = unauth_client.get(
        URL + "/1/review", params={"source_name": "oracle_demis_mock"}
    )
    assert result.status_code == 401


@pytest.mark.parametrize("role", [
    "viewer", "auditor", "query_operator", "template_author", "template_approver",
])
def test_get_review_available_to_catalog_read_without_target_override(
    unauth_client, monkeypatch, role,
):
    _history(monkeypatch)
    result = unauth_client.get(
        URL + "/1/review",
        params={"source_name": "oracle_demis_mock"},
        headers={"X-DQA-Dev-Actor": "reader", "X-DQA-Dev-Roles": role},
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["review_status"] == "REVIEW_REQUIRED"
    assert body["candidate_package_valid"] is True
    assert body["preflight_status"] == "NOT_VERIFIED"
    assert body["activation_eligible"] is False
    assert "snapshot_json" not in result.text
    assert "capture_request_id" not in result.text


def test_get_review_unknown_source_404(client, monkeypatch):
    _history(monkeypatch)
    result = client.get(
        URL + "/1/review",
        params={"source_name": "another_source"},
    )
    assert result.status_code == 404
    assert result.json()["detail"]["code"] == "SNAPSHOT_REVISION_NOT_FOUND"


def test_get_review_invalid_source_422(client, monkeypatch):
    _history(monkeypatch)
    response = client.get(
        URL + "/1/review", params={"source_name": "../wrong"},
    )
    assert response.status_code == 422


def test_get_review_corrupt_row_no_leak(client, monkeypatch):
    db = _history(monkeypatch)
    db.rows[0].snapshot_json["columns"][0]["column_comment"] = "TOP_SECRET_VALUE"
    response = client.get(
        URL + "/1/review", params={"source_name": "oracle_demis_mock"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SNAPSHOT_REVIEW_UNVERIFIABLE"
    assert "TOP_SECRET_VALUE" not in response.text
