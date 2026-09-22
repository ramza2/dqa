"""Active Catalog query API integration tests."""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryErrorCode
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from tests.catalog_package_fixtures import DEFAULT_SOURCE

pytestmark = pytest.mark.integration

SOURCE_A = dict(DEFAULT_SOURCE)
SOURCE_B = {
    "source_name": "oracle_demis_other",
    "db_type": "oracle",
    "database_name": "FREEPDB1",
    "default_schema": "DEMIS_OTHER",
}


def _query_catalog_docs(*, fingerprint: str = "fp-query-a") -> dict[str, Any]:
    """Producer-style metadata used by Catalog Query API tests."""
    tables = [
        {
            "schema": "DEMIS_OWNER",
            "name": "TB_ADM_HIST",
            "comment": "환자 입원 이력",
            "type": "TABLE",
        },
        {
            "schema": "DEMIS_OWNER",
            "name": "TB_WARD",
            "comment": "병동 마스터",
            "type": "TABLE",
        },
        {
            "schema": "OTHER_OWNER",
            "name": "TB_ADM_HIST",
            "comment": "other schema admission",
            "type": "TABLE",
        },
    ]
    columns = [
        {
            "schema": "DEMIS_OWNER",
            "table": "TB_ADM_HIST",
            "name": "ADM_ID",
            "ordinal": 1,
            "data_type": "NUMBER",
            "nullable": False,
            "is_primary_key": True,
            "is_unique": True,
            "comment": "입원 ID",
        },
        {
            "schema": "DEMIS_OWNER",
            "table": "TB_ADM_HIST",
            "name": "WARD_CD",
            "ordinal": 2,
            "data_type": "VARCHAR2",
            "nullable": True,
            "is_primary_key": False,
            "is_unique": False,
            "comment": "입원 병동 코드",
        },
        {
            "schema": "DEMIS_OWNER",
            "table": "TB_WARD",
            "name": "WARD_CD",
            "ordinal": 1,
            "data_type": "VARCHAR2",
            "nullable": False,
            "is_primary_key": True,
            "is_unique": True,
            "comment": "병동 코드",
        },
        {
            "schema": "OTHER_OWNER",
            "table": "TB_ADM_HIST",
            "name": "ADM_ID",
            "ordinal": 1,
            "data_type": "NUMBER",
            "nullable": False,
            "is_primary_key": True,
            "comment": "other adm id",
        },
    ]
    relations = [
        {
            "name": "FK_ADM_WARD",
            "schema": "DEMIS_OWNER",
            "table": "TB_ADM_HIST",
            "referenced_schema": "DEMIS_OWNER",
            "referenced_table": "TB_WARD",
            "columns": [{"column": "WARD_CD", "referenced_column": "WARD_CD"}],
        },
        {
            "name": "FK_OTHER",
            "schema": "OTHER_OWNER",
            "table": "TB_ADM_HIST",
            "referenced_schema": "OTHER_OWNER",
            "referenced_table": "TB_OTHER",
            "columns": [{"column": "ADM_ID", "referenced_column": "ID"}],
        },
    ]
    indexes = [
        {
            "name": "PK_ADM",
            "schema": "DEMIS_OWNER",
            "table": "TB_ADM_HIST",
            "unique": True,
            "columns": ["ADM_ID"],
        },
        {
            "name": "IX_ADM_WARD",
            "schema": "DEMIS_OWNER",
            "table": "TB_ADM_HIST",
            "unique": False,
            "columns": ["WARD_CD"],
        },
        {
            "name": "PK_WARD",
            "schema": "DEMIS_OWNER",
            "table": "TB_WARD",
            "unique": True,
            "columns": ["WARD_CD"],
        },
    ]
    categories = [
        {"id": "admission", "name": "Admission", "description": "입원 관련"},
        {"id": "ward", "name": "Ward", "description": "병동 관련"},
    ]
    # categories.json assignments are injected via mutate after build_package_zip files.
    return {
        "tables": tables,
        "columns": columns,
        "relations": relations,
        "indexes": indexes,
        "categories": categories,
        "fingerprint": fingerprint,
    }


def _import_and_activate(
    session: Session,
    *,
    source: dict[str, Any] | None = None,
    fingerprint: str = "fp-query-a",
    activate: bool = True,
) -> Any:
    import json

    from tests.catalog_package_fixtures import build_core_documents, build_package_zip as _build

    meta = _query_catalog_docs(fingerprint=fingerprint)
    files = build_core_documents(
        source=source or SOURCE_A,
        fingerprint=fingerprint,
        tables=meta["tables"],
        columns=meta["columns"],
        relations=meta["relations"],
        indexes=meta["indexes"],
        categories=meta["categories"],
    )
    categories_payload = json.loads(files["categories.json"])
    categories_payload["table_assignments"] = [
        {
            "category_id": "admission",
            "schema": "DEMIS_OWNER",
            "table": "TB_ADM_HIST",
            "provenance": "MANUAL",
        },
        {
            "category_id": "ward",
            "schema": "DEMIS_OWNER",
            "table": "TB_WARD",
            "provenance": "AUTO",
        },
    ]
    files["categories.json"] = json.dumps(
        categories_payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")

    archive = _build(
        package_readiness="READY",
        source=source or SOURCE_A,
        fingerprint=fingerprint,
        files=files,
    )
    revision, created = import_catalog_package_bytes(archive, session)
    assert created is True
    session.flush()
    if activate:
        activate_catalog_revision(session, revision.id)
        session.flush()
    return revision


def _assert_envelope(payload: dict[str, Any], *, source_name: str, revision_id: int, fingerprint: str) -> None:
    assert payload["source_name"] == source_name
    assert payload["revision_id"] == revision_id
    assert payload["schema_fingerprint"] == fingerprint
    assert "manifest_json" not in payload
    assert "database_json" not in payload
    assert "tables_json" not in payload
    assert "schema_snapshot_json" not in payload
    assert "managed_file_digests_json" not in payload


def test_active_catalog_entity_lists(
    db_session: Session, db_client: TestClient
) -> None:
    revision = _import_and_activate(db_session, fingerprint="fp-query-list")
    db_session.commit()
    source = SOURCE_A["source_name"]

    tables = db_client.get(f"/api/v1/catalog/active/{source}/tables")
    assert tables.status_code == 200
    body = tables.json()
    _assert_envelope(body, source_name=source, revision_id=revision.id, fingerprint="fp-query-list")
    assert body["total"] == 3
    assert len(body["items"]) == 3

    columns = db_client.get(f"/api/v1/catalog/active/{source}/columns")
    assert columns.status_code == 200
    assert columns.json()["total"] == 4

    relations = db_client.get(f"/api/v1/catalog/active/{source}/relations")
    assert relations.status_code == 200
    assert relations.json()["total"] == 2
    assert relations.json()["items"][0]["columns"][0]["column"] == "WARD_CD"

    indexes = db_client.get(f"/api/v1/catalog/active/{source}/indexes")
    assert indexes.status_code == 200
    assert indexes.json()["total"] == 3
    assert any(item["columns"] == ["ADM_ID"] for item in indexes.json()["items"])

    categories = db_client.get(f"/api/v1/catalog/active/{source}/categories")
    assert categories.status_code == 200
    assert categories.json()["total"] == 2
    assert categories.json()["items"][0]["assignments"]


def test_active_missing_and_inactive_revision(
    db_session: Session, db_client: TestClient
) -> None:
    missing = db_client.get("/api/v1/catalog/active/no_source/tables")
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND

    revision = _import_and_activate(db_session, fingerprint="fp-inactive", activate=False)
    db_session.commit()
    response = db_client.get(f"/api/v1/catalog/active/{SOURCE_A['source_name']}/tables")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND
    # Import history still works for inactive revision.
    detail = db_client.get(f"/api/v1/catalog/imports/{revision.id}")
    assert detail.status_code == 200


def test_tables_and_columns_q_search(db_session: Session, db_client: TestClient) -> None:
    revision = _import_and_activate(db_session, fingerprint="fp-search")
    db_session.commit()
    source = SOURCE_A["source_name"]

    by_name = db_client.get(f"/api/v1/catalog/active/{source}/tables", params={"q": "ward"})
    assert by_name.status_code == 200
    assert by_name.json()["total"] == 1
    assert by_name.json()["items"][0]["name"] == "TB_WARD"

    by_comment = db_client.get(
        f"/api/v1/catalog/active/{source}/tables", params={"q": "입원 이력"}
    )
    assert by_comment.json()["total"] == 1
    assert by_comment.json()["items"][0]["name"] == "TB_ADM_HIST"

    col_q = db_client.get(
        f"/api/v1/catalog/active/{source}/columns", params={"q": "병동 코드"}
    )
    assert col_q.status_code == 200
    names = {item["name"] for item in col_q.json()["items"]}
    assert "WARD_CD" in names
    _assert_envelope(
        col_q.json(), source_name=source, revision_id=revision.id, fingerprint="fp-search"
    )


def test_filters_pagination_sort_and_detail(
    db_session: Session, db_client: TestClient
) -> None:
    revision = _import_and_activate(db_session, fingerprint="fp-filter")
    db_session.commit()
    source = SOURCE_A["source_name"]

    schema_filtered = db_client.get(
        f"/api/v1/catalog/active/{source}/tables",
        params={"schema_name": "DEMIS_OWNER"},
    )
    assert schema_filtered.json()["total"] == 2

    category_filtered = db_client.get(
        f"/api/v1/catalog/active/{source}/tables",
        params={"category": "admission"},
    )
    assert category_filtered.json()["total"] == 1
    assert category_filtered.json()["items"][0]["name"] == "TB_ADM_HIST"

    cols = db_client.get(
        f"/api/v1/catalog/active/{source}/columns",
        params={"table_name": "TB_ADM_HIST", "schema_name": "DEMIS_OWNER"},
    )
    assert cols.json()["total"] == 2
    assert [c["name"] for c in cols.json()["items"]] == ["ADM_ID", "WARD_CD"]

    rel_src = db_client.get(
        f"/api/v1/catalog/active/{source}/relations",
        params={"table_name": "TB_ADM_HIST", "schema_name": "DEMIS_OWNER"},
    )
    assert rel_src.json()["total"] == 1

    rel_tgt = db_client.get(
        f"/api/v1/catalog/active/{source}/relations",
        params={"referenced_table_name": "TB_WARD"},
    )
    assert rel_tgt.json()["total"] == 1

    idx = db_client.get(
        f"/api/v1/catalog/active/{source}/indexes",
        params={"table_name": "TB_ADM_HIST", "unique": True},
    )
    assert idx.json()["total"] == 1
    assert idx.json()["items"][0]["name"] == "PK_ADM"

    cat_q = db_client.get(
        f"/api/v1/catalog/active/{source}/categories",
        params={"q": "입원"},
    )
    assert cat_q.json()["total"] == 1
    assert cat_q.json()["items"][0]["id"] == "admission"

    page = db_client.get(
        f"/api/v1/catalog/active/{source}/tables",
        params={"limit": 1, "offset": 1},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 1
    assert len(page.json()["items"]) == 1

    # Deterministic sort: OTHER_OWNER before DEMIS? casefold schema then name.
    all_tables = db_client.get(f"/api/v1/catalog/active/{source}/tables").json()["items"]
    keys = [(t["schema_name"], t["name"]) for t in all_tables]
    assert keys == sorted(keys, key=lambda x: (x[0].casefold(), x[1].casefold()))

    detail = db_client.get(
        f"/api/v1/catalog/active/{source}/tables/DEMIS_OWNER/TB_ADM_HIST"
    )
    assert detail.status_code == 200
    assert detail.json()["item"]["name"] == "TB_ADM_HIST"
    assert detail.json()["revision_id"] == revision.id

    missing = db_client.get(
        f"/api/v1/catalog/active/{source}/tables/DEMIS_OWNER/NO_SUCH_TABLE"
    )
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == CatalogQueryErrorCode.TABLE_NOT_FOUND


def test_revision_switch_updates_query_results(
    db_session: Session, db_client: TestClient
) -> None:
    rev1 = _import_and_activate(db_session, fingerprint="fp-sw-q1")
    db_session.commit()
    source = SOURCE_A["source_name"]

    before = db_client.get(f"/api/v1/catalog/active/{source}/tables").json()
    assert before["revision_id"] == rev1.id
    assert before["total"] == 3
    old_tables_json = copy.deepcopy(rev1.tables_json)

    # Second revision with a single table.
    from tests.catalog_package_fixtures import build_core_documents, build_package_zip
    import json

    files = build_core_documents(
        source=SOURCE_A,
        fingerprint="fp-sw-q2",
        tables=[{"schema": "DEMIS_OWNER", "name": "ONLY_ONE", "comment": "solo"}],
        columns=[{"schema": "DEMIS_OWNER", "table": "ONLY_ONE", "name": "ID", "ordinal": 1}],
        relations=[],
        indexes=[],
        categories=[],
    )
    archive = build_package_zip(
        package_readiness="READY",
        source=SOURCE_A,
        fingerprint="fp-sw-q2",
        files=files,
    )
    rev2, created = import_catalog_package_bytes(archive, db_session)
    assert created is True
    activate_catalog_revision(db_session, rev2.id)
    db_session.commit()

    after = db_client.get(f"/api/v1/catalog/active/{source}/tables").json()
    assert after["revision_id"] == rev2.id
    assert after["schema_fingerprint"] == "fp-sw-q2"
    assert after["total"] == 1
    assert after["items"][0]["name"] == "ONLY_ONE"

    db_session.expire_all()
    from app.models.catalog_import import CatalogImportRevision

    still_old = db_session.get(CatalogImportRevision, rev1.id)
    assert still_old is not None
    assert still_old.tables_json == old_tables_json


def test_cross_source_isolation(db_session: Session, db_client: TestClient) -> None:
    rev_a = _import_and_activate(db_session, source=SOURCE_A, fingerprint="fp-iso-qa")
    # Source B with different table set.
    from tests.catalog_package_fixtures import build_core_documents, build_package_zip

    files_b = build_core_documents(
        source=SOURCE_B,
        fingerprint="fp-iso-qb",
        tables=[{"schema": "DEMIS_OTHER", "name": "TB_B_ONLY", "comment": "b only"}],
        columns=[],
        relations=[],
        indexes=[],
        categories=[],
    )
    archive_b = build_package_zip(
        package_readiness="READY",
        source=SOURCE_B,
        fingerprint="fp-iso-qb",
        files=files_b,
    )
    rev_b, created = import_catalog_package_bytes(archive_b, db_session)
    assert created is True
    activate_catalog_revision(db_session, rev_b.id)
    db_session.commit()

    a_tables = db_client.get(f"/api/v1/catalog/active/{SOURCE_A['source_name']}/tables").json()
    b_tables = db_client.get(f"/api/v1/catalog/active/{SOURCE_B['source_name']}/tables").json()
    assert a_tables["revision_id"] == rev_a.id
    assert b_tables["revision_id"] == rev_b.id
    assert {t["name"] for t in a_tables["items"]} != {t["name"] for t in b_tables["items"]}
    assert b_tables["items"][0]["name"] == "TB_B_ONLY"


def test_response_excludes_raw_package_documents(
    db_session: Session, db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-raw")
    db_session.commit()
    source = SOURCE_A["source_name"]
    for path in ("tables", "columns", "relations", "indexes", "categories"):
        payload = db_client.get(f"/api/v1/catalog/active/{source}/{path}").json()
        dumped = str(payload)
        assert "manifest_json" not in dumped
        assert "schema_snapshot_json" not in dumped
        assert "managed_file_digests" not in dumped
        assert "preflight_json" not in dumped
