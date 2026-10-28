"""Synthetic M2-2D schema ZIP part tests; no Oracle or physical DB access."""
from copy import deepcopy
from dataclasses import replace
from io import BytesIO
import hashlib
import json
from zipfile import ZipFile

import pytest

from app.adapters.schema_inspector.base import InspectedForeignKey, InspectedForeignKeyColumn
from app.services.schema_snapshot_schema_bundle import (
    SnapshotSchemaBundleError, build_snapshot_schema_zip,
)
from tests.test_schema_snapshot_history import FakeSession, _base, _capture

URL = "/api/v1/schema-inspector/snapshots/1/schema-report.zip"
SCHEMA = "DEMIS_OWNER"
TABLE_NAMES = ["TB_ALPHA", "TB_BETA", "TB_GAMMA"]


def _stored():
    snap = deepcopy(_base())
    original_table = snap.tables[0]
    original_cols = snap.columns
    snap.tables = [
        replace(original_table, table_name=name, table_comment="합성 테이블 " + name)
        for name in TABLE_NAMES
    ]
    snap.columns = [
        replace(col, table_name=name, default_value="SECRET_SQL_DEFAULT_NEVER_EXPORT")
        for name in TABLE_NAMES for col in original_cols
    ]
    snap.foreign_keys = [
        InspectedForeignKey(
            schema_name=SCHEMA,
            constraint_name="FK_ALPHA_BETA",
            source_table="TB_ALPHA",
            target_schema=SCHEMA,
            target_table="TB_BETA",
            columns=(InspectedForeignKeyColumn(1, "ID", "ID"),),
        )
    ]
    db = FakeSession()
    return _capture(db, snapshot=snap).revision


def _zip_parts(blob: bytes):
    with ZipFile(BytesIO(blob), "r") as z:
        manifest = json.loads(z.read("manifest.json"))
        names = z.namelist()
        files = [(record, z.read(record["file"])) for record in manifest["files"]]
        readme = z.read("README.txt")
    return manifest, names, files, readme


def test_batched_export_is_deterministic_complete_and_manifest_source_bound():
    row = _stored()
    part1, total1, next1 = build_snapshot_schema_zip(
        row, schema_name=SCHEMA, offset=0, limit=2,
    )
    part2, total2, next2 = build_snapshot_schema_zip(
        row, schema_name=SCHEMA, offset=2, limit=2,
    )
    assert total1 == total2 == 3
    assert next1 == 2 and next2 is None
    one, names1, files1, readme = _zip_parts(part1)
    two, names2, files2, _ = _zip_parts(part2)
    assert [r["table_name"] for r in one["files"]] == TABLE_NAMES[:2]
    assert [r["table_name"] for r in two["files"]] == TABLE_NAMES[2:]
    assert one["source_name"] == row.source_name
    assert one["snapshot_revision_id"] == row.id
    assert one["schema_fingerprint"] == row.schema_fingerprint
    assert one["schema_name"] == SCHEMA
    assert one["preflight_status"] == "NOT_VERIFIED"
    assert one["activation_eligible"] is False
    assert one["exported_table_count"] == 2
    assert one["next_offset"] == 2
    assert two["next_offset"] is None
    assert names1 == ["tables/table-000001.docx", "tables/table-000002.docx", "manifest.json", "README.txt"]
    assert names2[0] == "tables/table-000003.docx"
    assert b"NOT_VERIFIED" in readme
    for r, blob in files1 + files2:
        assert blob.startswith(b"PK")
        assert hashlib.sha256(blob).hexdigest() == r["sha256"]
        with ZipFile(BytesIO(blob)) as document:
            core = document.read("word/document.xml")
            assert b"SECRET_SQL_DEFAULT_NEVER_EXPORT" not in core
    assert b"SECRET_SQL_DEFAULT_NEVER_EXPORT" not in part1 + part2


@pytest.mark.parametrize("offset,limit,code", [
    (3, 1, "SNAPSHOT_SCHEMA_EXPORT_RANGE_NOT_SATISFIABLE"),
    (0, 11, "SNAPSHOT_SCHEMA_EXPORT_INVALID_RANGE"),
    (-1, 1, "SNAPSHOT_SCHEMA_EXPORT_INVALID_RANGE"),
])
def test_invalid_part_fails_closed(offset, limit, code):
    row = _stored()
    with pytest.raises(SnapshotSchemaBundleError, match=code):
        build_snapshot_schema_zip(row, schema_name=SCHEMA, offset=offset, limit=limit)


def test_unknown_schema_does_not_export_or_fallback_to_another_schema():
    row = _stored()
    with pytest.raises(SnapshotSchemaBundleError, match="SCHEMA_NOT_FOUND"):
        build_snapshot_schema_zip(row, schema_name="OTHER_SCHEMA")


@pytest.mark.parametrize("damage", ["fingerprint", "counts", "payload", "version"])
def test_corrupt_snapshot_never_returns_part(damage):
    row = _stored()
    if damage == "fingerprint":
        row.schema_fingerprint = "0" * 64
    elif damage == "counts":
        row.counts_json["columns"] = 999
    elif damage == "payload":
        row.snapshot_json["tables"][0]["table_comment"] = "TOP_PRIVATE_COMMENT"
    elif damage == "version":
        row.snapshot_version = 99
    with pytest.raises(SnapshotSchemaBundleError, match="UNVERIFIABLE"):
        build_snapshot_schema_zip(row, schema_name=SCHEMA)


def test_zip_api_auth_403_scope_headers_and_416(unauth_client, client, monkeypatch):
    from app.api.routes import schema_snapshot_history as api
    row = _stored()
    monkeypatch.setattr(
        api, "get_snapshot_revision",
        lambda _session, revision_id, *, source_name:
            row if revision_id == row.id and source_name == row.source_name else None,
    )
    params = {"source_name": row.source_name, "schema_name": SCHEMA, "offset": 0, "limit": 2}
    assert unauth_client.get(URL, params=params).status_code == 401
    viewer = unauth_client.get(
        URL, params=params,
        headers={"X-DQA-Dev-Actor": "reader", "X-DQA-Dev-Roles": "viewer"},
    )
    assert viewer.status_code == 403

    response = client.get(URL, params=params)
    assert response.status_code == 200, response.text[:200] if response.status_code != 200 else ""
    assert response.headers["content-type"].startswith("application/zip")
    assert response.headers["x-dqa-schema-total-tables"] == "3"
    assert response.headers["x-dqa-schema-next-offset"] == "2"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "attachment;" in response.headers["content-disposition"]
    assert _zip_parts(response.content)[0]["exported_table_count"] == 2
    last = client.get(URL, params={**params, "offset": 2})
    assert last.status_code == 200
    assert last.headers["x-dqa-schema-next-offset"] == "-1"
    invalid = client.get(URL, params={**params, "offset": 3})
    assert invalid.status_code == 416
    assert invalid.json()["detail"]["code"] == "SNAPSHOT_SCHEMA_EXPORT_RANGE_NOT_SATISFIABLE"
    assert client.get(URL, params={**params, "source_name": "wrong"}).status_code == 404
    assert client.get(URL, params={**params, "limit": 11}).status_code == 422


def test_corrupt_endpoint_reports_sanitized_409(client, monkeypatch):
    from app.api.routes import schema_snapshot_history as api
    row = _stored()
    row.snapshot_json["tables"][0]["table_comment"] = "PRIVATE_TEXT"
    monkeypatch.setattr(api, "get_snapshot_revision", lambda *args, **kwargs: row)
    response = client.get(URL, params={"source_name": row.source_name, "schema_name": SCHEMA})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SNAPSHOT_SCHEMA_EXPORT_UNVERIFIABLE"
    assert "PRIVATE_TEXT" not in response.text
