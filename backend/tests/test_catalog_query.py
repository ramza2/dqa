"""Active Catalog query API integration tests (Schema Analyzer v2 producer shapes)."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryErrorCode
from app.models.catalog_import import CatalogImportRevision
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from tests.catalog_package_fixtures import DEFAULT_SOURCE, build_core_documents, build_package_zip

pytestmark = pytest.mark.integration

SOURCE_A = dict(DEFAULT_SOURCE)
SOURCE_B = {
    "source_name": "oracle_demis_other",
    "db_type": "oracle",
    "database_name": "FREEPDB1",
    "default_schema": "DEMIS_OTHER",
}


def _query_catalog_docs(*, fingerprint: str = "fp-query-a") -> dict[str, Any]:
    """Canonical Schema Analyzer Catalog Package v2 producer metadata."""
    tables = [
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_ADM_HIST",
            "table_type": "TABLE",
            "table_comment": "환자 입원 이력",
            "comment_provenance": "DB_COMMENT",
            "object_fingerprint": "fp-tbl-adm",
            "key_constraints": [],
            "categories": ["admission"],
        },
        {
            "table_key": "DEMIS_OWNER.TB_WARD",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_WARD",
            "table_type": "TABLE",
            "table_comment": "병동 마스터",
            "comment_provenance": "DB_COMMENT",
            "object_fingerprint": "fp-tbl-ward",
            "key_constraints": [],
            "categories": ["ward"],
        },
        {
            "table_key": "OTHER_OWNER.TB_ADM_HIST",
            "schema_name": "OTHER_OWNER",
            "table_name": "TB_ADM_HIST",
            "table_type": "TABLE",
            "table_comment": "other schema admission",
            "comment_provenance": "DB_COMMENT",
            "object_fingerprint": "fp-tbl-other",
            "key_constraints": [],
            "categories": [],
        },
    ]
    columns = [
        {
            "column_key": "DEMIS_OWNER.TB_ADM_HIST.ADM_ID",
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "ordinal_position": 1,
            "column_name": "ADM_ID",
            "data_type": "NUMBER",
            "nullable": False,
            "default_value": None,
            "column_comment": "입원 ID",
            "primary_key": True,
            "unique": True,
            "object_fingerprint": "fp-col-adm-id",
        },
        {
            "column_key": "DEMIS_OWNER.TB_ADM_HIST.WARD_CD",
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "ordinal_position": 2,
            "column_name": "WARD_CD",
            "data_type": "VARCHAR2",
            "nullable": True,
            "default_value": None,
            "column_comment": "입원 병동 코드",
            "primary_key": False,
            "unique": False,
            "object_fingerprint": "fp-col-ward-cd",
        },
        {
            "column_key": "DEMIS_OWNER.TB_WARD.WARD_CD",
            "table_key": "DEMIS_OWNER.TB_WARD",
            "ordinal_position": 1,
            "column_name": "WARD_CD",
            "data_type": "VARCHAR2",
            "nullable": False,
            "default_value": None,
            "column_comment": "병동 코드",
            "primary_key": True,
            "unique": True,
            "object_fingerprint": "fp-col-ward-pk",
        },
        {
            "column_key": "OTHER_OWNER.TB_ADM_HIST.ADM_ID",
            "table_key": "OTHER_OWNER.TB_ADM_HIST",
            "ordinal_position": 1,
            "column_name": "ADM_ID",
            "data_type": "NUMBER",
            "nullable": False,
            "default_value": None,
            "column_comment": "other adm id",
            "primary_key": True,
            "unique": True,
            "object_fingerprint": "fp-col-other",
        },
    ]
    relations = [
        {
            "relation_key": "DEMIS_OWNER.TB_ADM_HIST::FK_ADM_WARD",
            "constraint_name": "FK_ADM_WARD",
            "relation_type": "FOREIGN_KEY",
            "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "target_table_key": "DEMIS_OWNER.TB_WARD",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "WARD_CD",
                    "target_column": "WARD_CD",
                }
            ],
            "object_fingerprint": "fp-rel-adm-ward",
        },
        {
            "relation_key": "OTHER_OWNER.TB_ADM_HIST::FK_OTHER",
            "constraint_name": "FK_OTHER",
            "relation_type": "FOREIGN_KEY",
            "source_table_key": "OTHER_OWNER.TB_ADM_HIST",
            "target_table_key": "OTHER_OWNER.TB_OTHER",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "ADM_ID",
                    "target_column": "ID",
                }
            ],
            "object_fingerprint": "fp-rel-other",
        },
    ]
    indexes = [
        {
            "index_key": "DEMIS_OWNER.TB_ADM_HIST::PK_ADM",
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "index_name": "PK_ADM",
            "unique": True,
            "index_method": "BTREE",
            "columns": ["ADM_ID"],
            "object_fingerprint": "fp-ix-pk-adm",
        },
        {
            "index_key": "DEMIS_OWNER.TB_ADM_HIST::IX_ADM_WARD",
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "index_name": "IX_ADM_WARD",
            "unique": False,
            "index_method": "BTREE",
            "columns": ["WARD_CD"],
            "object_fingerprint": "fp-ix-adm-ward",
        },
        {
            "index_key": "DEMIS_OWNER.TB_WARD::PK_WARD",
            "table_key": "DEMIS_OWNER.TB_WARD",
            "index_name": "PK_WARD",
            "unique": True,
            "index_method": "BTREE",
            "columns": ["WARD_CD"],
            "object_fingerprint": "fp-ix-pk-ward",
        },
    ]
    categories = [
        {
            "category_key": "admission",
            "category_name": "Admission",
            "description": "입원 관련",
            "sort_order": 10,
            "active": True,
            "definition_provenance": "CATALOG_CATEGORY",
        },
        {
            "category_key": "ward",
            "category_name": "Ward",
            "description": "병동 관련",
            "sort_order": 20,
            "active": True,
            "definition_provenance": "CATALOG_CATEGORY",
        },
    ]
    assignments = [
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "category_key": "admission",
            "is_primary": True,
            "assignment_source": "MANUAL",
            "confidence": None,
            "note": "primary admission table",
        },
        {
            "table_key": "DEMIS_OWNER.TB_WARD",
            "category_key": "ward",
            "is_primary": True,
            "assignment_source": "AUTO",
            "confidence": 0.9,
            "note": None,
        },
    ]
    return {
        "tables": tables,
        "columns": columns,
        "relations": relations,
        "indexes": indexes,
        "categories": categories,
        "assignments": assignments,
        "fingerprint": fingerprint,
    }


def _import_and_activate(
    session: Session,
    *,
    source: dict[str, Any] | None = None,
    fingerprint: str = "fp-query-a",
    activate: bool = True,
) -> CatalogImportRevision:
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
    categories_payload["table_assignments"] = meta["assignments"]
    files["categories.json"] = json.dumps(
        categories_payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")

    archive = build_package_zip(
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


def _assert_envelope(
    payload: dict[str, Any], *, source_name: str, revision_id: int, fingerprint: str
) -> None:
    assert payload["source_name"] == source_name
    assert payload["revision_id"] == revision_id
    assert payload["schema_fingerprint"] == fingerprint
    assert "manifest_json" not in payload
    assert "database_json" not in payload
    assert "tables_json" not in payload
    assert "schema_snapshot_json" not in payload
    assert "managed_file_digests_json" not in payload


def test_active_catalog_entity_lists(db_session: Session, db_client: TestClient) -> None:
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
    adm_rel = next(
        item for item in relations.json()["items"] if item["name"] == "FK_ADM_WARD"
    )
    assert adm_rel["columns"] == [{"column": "WARD_CD", "referenced_column": "WARD_CD"}]

    indexes = db_client.get(f"/api/v1/catalog/active/{source}/indexes")
    assert indexes.status_code == 200
    assert indexes.json()["total"] == 3
    assert any(item["columns"] == ["ADM_ID"] for item in indexes.json()["items"])

    categories = db_client.get(f"/api/v1/catalog/active/{source}/categories")
    assert categories.status_code == 200
    assert categories.json()["total"] == 2
    assignment = categories.json()["items"][0]["assignments"][0]
    assert assignment["provenance"] in {"MANUAL", "AUTO"}
    assert "is_primary" in assignment


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
    detail = db_client.get(f"/api/v1/catalog/imports/{revision.id}")
    assert detail.status_code == 200


def test_producer_comment_q_search_regressions(
    db_session: Session, db_client: TestClient
) -> None:
    revision = _import_and_activate(db_session, fingerprint="fp-search")
    db_session.commit()
    source = SOURCE_A["source_name"]

    by_table_comment = db_client.get(
        f"/api/v1/catalog/active/{source}/tables",
        params={"q": "환자 입원 이력"},
    )
    assert by_table_comment.status_code == 200
    assert by_table_comment.json()["total"] == 1
    assert by_table_comment.json()["items"][0]["name"] == "TB_ADM_HIST"

    by_name = db_client.get(f"/api/v1/catalog/active/{source}/tables", params={"q": "ward"})
    assert by_name.json()["total"] == 1
    assert by_name.json()["items"][0]["name"] == "TB_WARD"

    col_q = db_client.get(
        f"/api/v1/catalog/active/{source}/columns",
        params={"q": "입원 병동 코드"},
    )
    assert col_q.status_code == 200
    assert col_q.json()["total"] == 1
    assert col_q.json()["items"][0]["name"] == "WARD_CD"
    assert col_q.json()["items"][0]["table_name"] == "TB_ADM_HIST"
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
    assert cols.json()["items"][1]["ordinal"] == 2
    assert cols.json()["items"][1]["is_primary_key"] is False

    rel_src = db_client.get(
        f"/api/v1/catalog/active/{source}/relations",
        params={"table_name": "TB_ADM_HIST", "schema_name": "DEMIS_OWNER"},
    )
    assert rel_src.json()["total"] == 1
    assert rel_src.json()["items"][0]["name"] == "FK_ADM_WARD"
    assert rel_src.json()["items"][0]["columns"] == [
        {"column": "WARD_CD", "referenced_column": "WARD_CD"}
    ]

    rel_tgt = db_client.get(
        f"/api/v1/catalog/active/{source}/relations",
        params={"referenced_table_name": "TB_WARD"},
    )
    assert rel_tgt.json()["total"] == 1

    idx = db_client.get(
        f"/api/v1/catalog/active/{source}/indexes",
        params={"schema_name": "DEMIS_OWNER", "table_name": "TB_ADM_HIST", "unique": True},
    )
    assert idx.json()["total"] == 1
    assert idx.json()["items"][0]["name"] == "PK_ADM"
    assert idx.json()["items"][0]["method"] == "BTREE"

    cat_q = db_client.get(
        f"/api/v1/catalog/active/{source}/categories",
        params={"q": "입원"},
    )
    assert cat_q.json()["total"] == 1
    assert cat_q.json()["items"][0]["id"] == "admission"
    assert cat_q.json()["items"][0]["name"] == "Admission"
    assert cat_q.json()["items"][0]["assignments"][0]["table_name"] == "TB_ADM_HIST"
    assert cat_q.json()["items"][0]["assignments"][0]["provenance"] == "MANUAL"

    page = db_client.get(
        f"/api/v1/catalog/active/{source}/tables",
        params={"limit": 1, "offset": 1},
    )
    assert page.status_code == 200
    assert page.json()["total"] == 3
    assert page.json()["limit"] == 1
    assert page.json()["offset"] == 1
    assert len(page.json()["items"]) == 1

    all_tables = db_client.get(f"/api/v1/catalog/active/{source}/tables").json()["items"]
    keys = [(t["schema_name"], t["name"]) for t in all_tables]
    assert keys == sorted(keys, key=lambda x: (x[0].casefold(), x[1].casefold()))

    detail = db_client.get(
        f"/api/v1/catalog/active/{source}/tables/DEMIS_OWNER/TB_ADM_HIST"
    )
    assert detail.status_code == 200
    assert detail.json()["item"]["name"] == "TB_ADM_HIST"
    assert detail.json()["item"]["comment"] == "환자 입원 이력"
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

    files = build_core_documents(
        source=SOURCE_A,
        fingerprint="fp-sw-q2",
        tables=[
            {
                "table_key": "DEMIS_OWNER.ONLY_ONE",
                "schema_name": "DEMIS_OWNER",
                "table_name": "ONLY_ONE",
                "table_type": "TABLE",
                "table_comment": "solo",
                "categories": [],
            }
        ],
        columns=[
            {
                "column_key": "DEMIS_OWNER.ONLY_ONE.ID",
                "table_key": "DEMIS_OWNER.ONLY_ONE",
                "ordinal_position": 1,
                "column_name": "ID",
                "data_type": "NUMBER",
                "nullable": False,
                "primary_key": True,
                "unique": True,
                "column_comment": None,
            }
        ],
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
    still_old = db_session.get(CatalogImportRevision, rev1.id)
    assert still_old is not None
    assert still_old.tables_json == old_tables_json


def test_cross_source_isolation(db_session: Session, db_client: TestClient) -> None:
    rev_a = _import_and_activate(db_session, source=SOURCE_A, fingerprint="fp-iso-qa")
    files_b = build_core_documents(
        source=SOURCE_B,
        fingerprint="fp-iso-qb",
        tables=[
            {
                "table_key": "DEMIS_OTHER.TB_B_ONLY",
                "schema_name": "DEMIS_OTHER",
                "table_name": "TB_B_ONLY",
                "table_type": "TABLE",
                "table_comment": "b only",
                "categories": [],
            }
        ],
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
