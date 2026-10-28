"""M2-2B safe Snapshot ERD projection; only synthetic in-memory objects."""
from copy import deepcopy
from dataclasses import replace

import pytest

from app.adapters.schema_inspector.base import InspectedForeignKey, InspectedForeignKeyColumn
from app.services.schema_snapshot_erd import SnapshotErdError, build_snapshot_erd
from tests.test_schema_snapshot_history import FakeSession, _base, _capture


def _stored():
    snapshot = deepcopy(_base())
    snapshot.foreign_keys = [
        InspectedForeignKey(
            schema_name="DEMIS_OWNER", constraint_name="FK_MOCK_REFERENCE",
            source_table="TB_MOCK", target_schema="OTHER_SCHEMA",
            target_table="TB_EXTERNAL",
            columns=(
                InspectedForeignKeyColumn(2, "SITE", "SITE"),
                InspectedForeignKeyColumn(1, "ID", "REF_ID"),
            ),
        ),
    ]
    db = FakeSession()
    row = _capture(db, snapshot=snapshot).revision
    return row


def test_snapshot_erd_preserves_composite_mapping_external_boundary_and_no_activation():
    row = _stored()
    result = build_snapshot_erd(
        row, focus_schema="DEMIS_OWNER", focus_table="TB_MOCK",
    )
    assert result["total_tables"] == 1
    assert result["tables"] == [{"schema_name": "DEMIS_OWNER", "table_name": "TB_MOCK"}]
    assert result["total_edges"] == 1
    assert result["edges"][0]["direction"] == "OUT"
    assert result["edges"][0]["referenced_only"] is True
    assert result["edges"][0]["column_mapping"] == [
        {"source": "ID", "target": "REF_ID"},
        {"source": "SITE", "target": "SITE"},
    ]
    assert result["preflight_status"] == "NOT_VERIFIED"
    assert result["activation_eligible"] is False
    assert "snapshot_json" not in str(result)
    assert "columns" not in result  # no raw column record or SQL default
    assert len(row.snapshot_json["columns"]) == 2


def test_list_filter_and_no_focus_requires_no_graph():
    row = _stored()
    result = build_snapshot_erd(row, query="mock", offset=0, limit=30)
    assert result["total_tables"] == 1
    assert result["total_edges"] == 0
    assert result["edges"] == []
    result = build_snapshot_erd(row, query="unmatched")
    assert result["total_tables"] == 0
    assert result["tables"] == []


def test_missing_focus_and_missing_schema_fail_closed():
    row = _stored()
    with pytest.raises(SnapshotErdError, match="SNAPSHOT_ERD_INVALID_FOCUS"):
        build_snapshot_erd(row, focus_table="TB_MOCK")
    with pytest.raises(SnapshotErdError, match="SNAPSHOT_ERD_TABLE_NOT_FOUND"):
        build_snapshot_erd(row, focus_schema="OTHER_SCHEMA", focus_table="TB_MOCK")


@pytest.mark.parametrize("damage", ["fingerprint", "counts", "version", "payload", "identity"])
def test_tampered_snapshot_never_exposes_graph(damage):
    row = _stored()
    if damage == "fingerprint":
        row.schema_fingerprint = "f" * 64
    elif damage == "counts":
        row.counts_json["foreign_keys"] = 999
    elif damage == "version":
        row.snapshot_version = 3
    elif damage == "payload":
        row.snapshot_json["tables"][0]["table_comment"] = "PRIVATE_VALUE"
    elif damage == "identity":
        row.schema_name = "OTHER_SCHEMA"
    with pytest.raises(SnapshotErdError, match="SNAPSHOT_ERD_UNVERIFIABLE"):
        build_snapshot_erd(row, focus_schema="DEMIS_OWNER", focus_table="TB_MOCK")


def test_endpoint_auth_source_scope_and_sanitized_409(unauth_client, client, monkeypatch):
    from app.api.routes import schema_snapshot_history as api

    row = _stored()
    monkeypatch.setattr(api, "get_snapshot_revision",
                        lambda _session, revision_id, *, source_name:
                        row if revision_id == row.id and source_name == row.source_name else None)
    url = "/api/v1/schema-inspector/snapshots/1/erd"
    params = {"source_name": row.source_name}
    assert unauth_client.get(url, params=params).status_code == 401
    result = client.get(url, params={
        **params, "focus_schema": "DEMIS_OWNER", "focus_table": "TB_MOCK",
    })
    assert result.status_code == 200, result.text
    assert result.json()["total_edges"] == 1
    assert "snapshot_json" not in result.text
    assert "default_value" not in result.text
    assert client.get(url, params={"source_name": "other_source"}).status_code == 404
    row.snapshot_json["tables"][0]["table_comment"] = "TOP_SECRET_VALUE"
    refused = client.get(url, params=params)
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "SNAPSHOT_ERD_UNVERIFIABLE"
    assert "TOP_SECRET_VALUE" not in refused.text
