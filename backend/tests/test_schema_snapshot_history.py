"""S-04-B offline service/HTTP tests; never connect to Oracle or write DQA DB."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.adapters.schema_inspector.base import InspectedColumn, InspectedTable, SchemaSnapshot
from app.models.schema_snapshot_revision import SchemaSnapshotRevision
from app.services.schema_snapshot_history import (
    SnapshotHistoryError, _snapshot_from_payload,
    capture_snapshot_revision,
)
from app.services.schema_catalog_candidate import _physical_payload


class FakeSession:
    """Simulates serialization and ORM session identity for pure unit tests.

    Real PostgreSQL advisory lock/CAS/DDL require a separate isolated PG test.
    """

    def __init__(self):
        self.rows = []
        self.lock_calls = []

    def execute(self, stmt, params=None):
        assert "pg_advisory_xact_lock" in str(stmt)
        self.lock_calls.append(params["lock_key"])

    def scalar(self, stmt):
        rendered = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        if "WHERE schema_snapshot_revisions.source_name =" in rendered and\
            "AND schema_snapshot_revisions.capture_request_id =" in rendered:
            for row in self.rows:
                if row.capture_request_id in rendered:
                    return row
            return None
        if "ORDER BY" in rendered:
            return self.rows[-1] if self.rows else None
        raise AssertionError("unexpected query")

    def add(self, row):
        self.rows.append(row)

    def flush(self):
        for index, row in enumerate(self.rows, 1):
            if row.id is None:
                row.id = index


def _base():
    def column(name, ordinal):
        return InspectedColumn(
            schema_name="DEMIS_OWNER", table_name="TB_MOCK",
            ordinal_position=ordinal, column_name=name, data_type="VARCHAR2",
            character_maximum_length=20, numeric_precision=None, numeric_scale=None,
            is_nullable=True, default_value=None, column_comment="합성 데이터",
        )
    return SchemaSnapshot(
        db_type="oracle", database_name="FREEPDB1", schema_name="DEMIS_OWNER",
        tables=[InspectedTable("DEMIS_OWNER", "TB_MOCK", "BASE TABLE", "테스트")],
        columns=[column("ID", 1), column("CODE", 2)],
    )


def _capture(session, snapshot=None, expected=None, request_id=None, source="oracle_demis_mock", actor="operator-1"):
    return capture_snapshot_revision(
        session, snapshot or _base(),
        source_name=source, captured_by=actor,
        capture_request_id=request_id or uuid4(),
        expected_previous_revision_id=expected,
    )


def test_first_capture_no_baseline_not_identical():
    db = FakeSession()
    saved = _capture(db)
    assert saved.created
    row = saved.revision
    assert row.id == 1
    assert row.previous_revision_id is None
    assert row.diff_summary_json["status"] == "NO_BASELINE"
    assert row.diff_summary_json["identical"] is None
    assert row.diff_summary_json["total_changes"] is None
    assert row.counts_json["tables"] == 1
    assert row.counts_json["columns"] == 2
    assert row.schema_fingerprint
    assert row.snapshot_json["columns"][0]["default_value"] is None
    assert db.lock_calls == ["dqa:snapshot:oracle_demis_mock"]


def test_second_capture_unchanged_is_new_append_revision():
    db = FakeSession()
    a = _capture(db).revision
    b = _capture(db, expected=a.id).revision
    assert b.id == 2
    assert b.previous_revision_id == a.id
    assert b.schema_fingerprint == a.schema_fingerprint
    assert b.diff_summary_json["status"] == "COMPARED"
    assert b.diff_summary_json["identical"] is True
    assert b.diff_summary_json["total_changes"] == 0
    assert len(db.rows) == 2


def test_modified_table_comment_and_type_are_recorded_without_values():
    db = FakeSession()
    a = _capture(db).revision
    newer = deepcopy(_base())
    newer.tables[0] = replace(newer.tables[0], table_comment="새 주석")
    newer.columns[0] = replace(newer.columns[0], data_type="NUMBER")
    b = _capture(db, newer, expected=a.id).revision
    diff = b.diff_summary_json
    assert diff["total_changes"] == 2
    assert diff["counts"]["TABLE"]["changed"] == 1
    assert diff["counts"]["COLUMN"]["changed"] == 1
    assert diff["changes"][0]["changed_fields"] == ["table_comment"]
    assert diff["changes"][1]["changed_fields"] == ["data_type"]
    assert "새 주석" not in str(diff)
    assert "NUMBER" not in str(diff)
    assert len(db.rows) == 2


def test_capture_request_replay_idempotent_but_conflicting_payload_rejected():
    db = FakeSession()
    req = uuid4()
    first = _capture(db, request_id=req)
    replay = _capture(db, request_id=req)
    assert replay.created is False
    assert replay.revision.id == first.revision.id
    assert len(db.rows) == 1

    altered = deepcopy(_base())
    altered.columns[0] = replace(altered.columns[0], data_type="NUMBER")
    with pytest.raises(SnapshotHistoryError, match="CAPTURE_REQUEST_REUSED"):
        _capture(db, snapshot=altered, request_id=req)


def test_stale_expected_revision_rejected_and_no_append():
    db = FakeSession()
    _capture(db)
    with pytest.raises(SnapshotHistoryError, match="STALE_SNAPSHOT_REVISION"):
        _capture(db, expected=None)
    assert len(db.rows) == 1


def test_target_identity_change_rejected_and_no_append():
    db = FakeSession()
    first = _capture(db).revision
    swapped = deepcopy(_base())
    swapped.database_name = "OTHER_PDB"
    with pytest.raises(SnapshotHistoryError, match="TARGET_IDENTITY_MISMATCH"):
        _capture(db, swapped, expected=first.id)
    assert len(db.rows) == 1


def test_corrupt_baseline_fails_closed():
    db = FakeSession()
    first = _capture(db).revision
    first.snapshot_json["tables"][0]["table_comment"] = "TAMPERED"
    with pytest.raises(SnapshotHistoryError, match="CORRUPT_BASELINE"):
        _capture(db, expected=first.id)
    assert len(db.rows) == 1


def test_default_sql_index_sql_excluded_from_saved_json():
    db = FakeSession()
    snap = _base()
    snap.columns[0] = replace(snap.columns[0], default_value="SENSITIVE_DEFAULT_EXPRESSION")
    row = _capture(db, snap).revision
    assert "SENSITIVE_DEFAULT_EXPRESSION" not in str(row.snapshot_json)
    assert "SENSITIVE_DEFAULT_EXPRESSION" not in str(row.diff_summary_json)


@pytest.mark.parametrize("kwargs,code", [
    ({"source": "../bad"}, "INVALID_SOURCE"),
    ({"actor": " "}, "INVALID_ACTOR"),
    ({"request_id": "not-a-uuid"}, "INVALID_CAPTURE_REQUEST_ID"),
    ({"expected": -1}, "INVALID_EXPECTED_REVISION"),
])
def test_fail_closed_invalid_capture_inputs(kwargs, code):
    db = FakeSession()
    with pytest.raises(SnapshotHistoryError, match=code):
        _capture(db, **kwargs)
    assert db.rows == []


def test_roundtrip_snapshot_payload_to_dto():
    snap = _base()
    restored = _snapshot_from_payload(_physical_payload(snap))
    assert restored == snap


def test_history_api_requires_identity(unauth_client):
    assert unauth_client.get(
        "/api/v1/schema-inspector/snapshots", params={"source_name": "oracle_demis_mock"}
    ).status_code == 401


@pytest.mark.parametrize("role", ["query_operator", "auditor", "viewer"])
def test_history_api_read_permission(unauth_client, monkeypatch, role):
    from app.api.routes import schema_snapshot_history as api

    db = FakeSession()
    row = _capture(db).revision
    row.captured_at = datetime.now(timezone.utc)
    monkeypatch.setattr(api, "list_snapshot_revisions", lambda session, **kwargs: [row])
    monkeypatch.setattr(api, "get_snapshot_revision", lambda session, revision_id, **kwargs: row)

    hdr = {"X-DQA-Dev-Actor": "reader", "X-DQA-Dev-Roles": role}
    result = unauth_client.get(
        "/api/v1/schema-inspector/snapshots", params={"source_name": "oracle_demis_mock"},
        headers=hdr,
    )
    assert result.status_code == 200
    assert result.json()[0]["id"] == 1
    assert "snapshot_json" not in result.text
    assert "capture_request_id" not in result.text

    detail = unauth_client.get(
        "/api/v1/schema-inspector/snapshots/1",
        params={"source_name": "oracle_demis_mock"},
        headers=hdr,
    )
    assert detail.status_code == 200
    assert detail.json()["diff_status"] == "NO_BASELINE"
    assert "snapshot_json" not in detail.text
    assert "capture_request_id" not in detail.text


def test_history_api_missing_source_returns_422(client):
    assert client.get("/api/v1/schema-inspector/snapshots").status_code == 422


def test_history_api_unknown_revision_404(client, monkeypatch):
    from app.api.routes import schema_snapshot_history as api
    monkeypatch.setattr(api, "get_snapshot_revision", lambda *args, **kwargs: None)
    resp = client.get(
        "/api/v1/schema-inspector/snapshots/999",
        params={"source_name": "oracle_demis_mock"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "SNAPSHOT_REVISION_NOT_FOUND"
