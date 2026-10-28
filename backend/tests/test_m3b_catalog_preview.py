"""M3-B — preview-only physical Catalog query, isolated synthetic PostgreSQL."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from tests.catalog_package_fixtures import DEFAULT_SOURCE, build_core_documents, build_package_zip

pytestmark = pytest.mark.integration
PATH = "/api/v1/query-builder/preview"
SOURCE = dict(DEFAULT_SOURCE)


def _fixture(session: Session, *, fingerprint: str = "fp-m3b"):
    files = build_core_documents(
        source=SOURCE, fingerprint=fingerprint,
        tables=[{"schema": "DEMIS_OWNER", "name": "T1"}],
        columns=[
            {"schema": "DEMIS_OWNER", "table": "T1", "name": "ID", "data_type": "NUMBER"},
            {"schema": "DEMIS_OWNER", "table": "T1", "name": "WARD_CD", "data_type": "VARCHAR2(20)"},
        ],
    )
    archive = build_package_zip(
        source=SOURCE, fingerprint=fingerprint, package_readiness="READY", files=files
    )
    rev, created = import_catalog_package_bytes(archive, session)
    assert created
    activate_catalog_revision(session, rev.id)
    session.commit()
    return rev


def _request(rev, **kwargs):
    obj = {
        "source_name": SOURCE["source_name"],
        "catalog_revision_id": rev.id,
        "schema_fingerprint": rev.schema_fingerprint,
        "schema_name": "DEMIS_OWNER",
        "table_name": "T1",
        "columns": ["ID", "WARD_CD"],
        "predicates": [{"column": "WARD_CD", "operator": "EQ"}],
        "row_limit": 50,
    }
    obj.update(kwargs)
    return obj


def test_preview_only_and_no_values_or_adapter(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    rev = _fixture(db_session)
    def no_adapter(*args, **kwargs):
        raise AssertionError("DEMIS adapter must not be called")
    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter", no_adapter
    )
    res = db_client.post(PATH, json=_request(rev))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source_name"] == SOURCE["source_name"]
    assert body["catalog_revision_id"] == rev.id
    assert body["preview_only"] is True
    assert body["executable"] is False and body["approved"] is False
    assert body["template_id"] is None
    assert body["parameters"] == [
        {"name": "p1", "column": "WARD_CD", "type": "string"},
        {"name": "p_limit", "column": None, "type": "integer"},
    ]
    assert body["sql_text"] == (
        'SELECT * FROM (SELECT "ID", "WARD_CD" FROM "DEMIS_OWNER"."T1" '
        'WHERE "WARD_CD" = :p1) q WHERE ROWNUM <= :p_limit'
    )
    assert res.headers["cache-control"] == "no-store, private"
    assert "password" not in res.text


@pytest.mark.parametrize("changes,status", [
    ({"schema_name": "BAD"}, 422),
    ({"columns": ["DOES_NOT_EXIST"]}, 422),
    ({"columns": ["ID", "ID"]}, 422),
    ({"columns": ['ID"; DROP TABLE X--']}, 422),
    ({"predicates": [{"column": "ID", "operator": "LIKE"}]}, 422),
    ({"predicates": [{"column": "WARD_CD", "operator": "UNKNOWN"}]}, 422),
    ({"row_limit": 101}, 422),
    ({"sql_text": "SELECT * FROM SECRET"}, 422),
    ({"catalog_revision_id": 9999}, 409),
    ({"schema_fingerprint": "stale"}, 409),
])
def test_preview_rejects_unknown_unsafe_and_stale(
    db_session: Session, db_client: TestClient, changes, status
):
    rev = _fixture(db_session)
    res = db_client.post(PATH, json=_request(rev, **changes))
    assert res.status_code == status, res.text
    assert "sql_text" not in res.json()
    if status == 409:
        assert res.json()["detail"]["code"] == "CATALOG_MISMATCH"


@pytest.mark.parametrize("role,status", [
    ("query_operator", 200), ("administrator", 200),
    ("viewer", 403), ("auditor", 403), ("template_author", 403),
])
def test_preview_rbac(
    db_session: Session, db_client: TestClient,
    unauth_db_client: TestClient, role, status,
):
    rev = _fixture(db_session)
    res = unauth_db_client.post(
        PATH, json=_request(rev),
        headers={"X-DQA-Dev-Actor": "tester", "X-DQA-Dev-Roles": role},
    )
    assert res.status_code == status


def test_preview_requires_auth(unauth_db_client: TestClient):
    res = unauth_db_client.post(PATH, json={
        "source_name": "s", "catalog_revision_id": 1,
        "schema_fingerprint": "x", "schema_name": "S", "table_name": "T",
        "columns": ["C"]
    })
    assert res.status_code == 401


def test_preview_null_predicate_has_no_unbound_parameter(
    db_session: Session, db_client: TestClient
):
    rev = _fixture(db_session)
    res = db_client.post(PATH, json=_request(rev, predicates=[
        {"column": "WARD_CD", "operator": "IS_NULL"}
    ]))
    assert res.status_code == 200, res.text
    assert '"WARD_CD" IS NULL' in res.json()["sql_text"]
    assert [p["name"] for p in res.json()["parameters"]] == ["p_limit"]
