"""Phase 27-A: Data Discovery domain contracts, builder, and persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domain.data_discovery import (
    BUILDER_VERSION,
    DiscoveryIdentityKind,
    DiscoveryObjectType,
    build_embedding_model_key,
    physical_document_key,
)
from app.models.catalog_import import CatalogImportRevision
from app.models.data_discovery import DataDiscoveryDocument
from app.repositories.data_discovery import DataDiscoveryRepository
from app.schemas.data_discovery import DataDiscoverySearchRequest, EmbeddingModelMetadata
from app.services.catalog_active import activate_catalog_revision
from app.services.data_discovery_document import (
    build_documents_for_revision,
    rebuild_for_active_source,
    rebuild_for_revision,
)

pytestmark = pytest.mark.integration

_HEAD = "20261008_dd01"


def _catalog_payload(*, fingerprint: str = "fp-dd-a") -> dict[str, Any]:
    tables = [
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_ADM_HIST",
            "table_type": "TABLE",
            "table_comment": "환자 입원 이력",
            "categories": ["admission"],
        },
        {
            "table_key": "DEMIS_OWNER.TB_WARD",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_WARD",
            "table_type": "TABLE",
            "table_comment": "병동 마스터",
            "categories": ["ward"],
        },
    ]
    columns = [
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "ordinal_position": 1,
            "column_name": "ADM_ID",
            "data_type": "NUMBER",
            "nullable": False,
            "column_comment": "입원 ID",
            "primary_key": True,
            "unique": True,
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "ordinal_position": 2,
            "column_name": "WARD_CD",
            "data_type": "VARCHAR2",
            "nullable": True,
            "column_comment": "입원 병동 코드",
            "primary_key": False,
            "unique": False,
        },
        {
            "table_key": "DEMIS_OWNER.TB_WARD",
            "ordinal_position": 1,
            "column_name": "WARD_CD",
            "data_type": "VARCHAR2",
            "nullable": False,
            "column_comment": "병동 코드",
            "primary_key": True,
            "unique": True,
        },
    ]
    relations = [
        {
            "constraint_name": "FK_ADM_WARD",
            "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "target_table_key": "DEMIS_OWNER.TB_WARD",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "WARD_CD",
                    "target_column": "WARD_CD",
                }
            ],
        }
    ]
    indexes = [
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "index_name": "PK_ADM",
            "unique": True,
            "index_method": "BTREE",
            "columns": ["ADM_ID"],
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "index_name": "IX_ADM_WARD",
            "unique": False,
            "index_method": "BTREE",
            "columns": ["WARD_CD"],
        },
    ]
    categories = [
        {
            "category_key": "admission",
            "category_name": "Admission",
            "description": "입원 관련",
        },
        {
            "category_key": "ward",
            "category_name": "Ward",
            "description": "병동 관련",
        },
    ]
    assignments = [
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "category_key": "admission",
            "is_primary": True,
            "assignment_source": "MANUAL",
        },
        {
            "table_key": "DEMIS_OWNER.TB_WARD",
            "category_key": "ward",
            "is_primary": True,
            "assignment_source": "AUTO",
        },
    ]
    return {
        "fingerprint": fingerprint,
        "tables": tables,
        "columns": columns,
        "relations": relations,
        "indexes": indexes,
        "categories": categories,
        "assignments": assignments,
    }


def _make_revision(
    session: Session,
    *,
    source_name: str = "oracle_demis_mock",
    fingerprint: str = "fp-dd-a",
    archive_sha256: str | None = None,
    payload: dict[str, Any] | None = None,
) -> CatalogImportRevision:
    data = payload or _catalog_payload(fingerprint=fingerprint)
    digest = archive_sha256 or ("a" * 64 if fingerprint == "fp-dd-a" else "b" * 64)
    if fingerprint == "fp-dd-b" and archive_sha256 is None:
        digest = "b" * 64
    revision = CatalogImportRevision(
        source_name=source_name,
        db_type="oracle",
        database_name="FREEPDB1",
        default_schema="DEMIS_OWNER",
        package_format="demis-catalog-package",
        package_version="2.0",
        package_readiness="READY",
        schema_fingerprint=data["fingerprint"],
        archive_sha256=digest,
        manifest_sha256="c" * 64,
        generated_at=datetime(2026, 10, 8, tzinfo=UTC),
        validation_status="VALID",
        table_count=len(data["tables"]),
        column_count=len(data["columns"]),
        relation_count=len(data["relations"]),
        index_count=len(data["indexes"]),
        category_count=len(data["categories"]),
        category_assignment_count=len(data["assignments"]),
        managed_file_count=1,
        manifest_json={"package_format": "demis-catalog-package"},
        database_json={"source": {"source_name": source_name}},
        tables_json={"tables": data["tables"]},
        columns_json={"columns": data["columns"]},
        relations_json={"relations": data["relations"]},
        indexes_json={"indexes": data["indexes"]},
        categories_json={
            "categories": data["categories"],
            "table_assignments": data["assignments"],
        },
        erd_json={},
        latest_run_json={},
        schema_snapshot_json={},
        preflight_json={},
        latest_diff_json={},
        managed_file_digests_json={},
    )
    session.add(revision)
    session.flush()
    session.refresh(revision)
    return revision


def test_physical_document_key_stable() -> None:
    assert (
        physical_document_key(
            DiscoveryObjectType.TABLE,
            schema_name="DEMIS_OWNER",
            table_name="TB_ADM_HIST",
        )
        == "TABLE:DEMIS_OWNER.TB_ADM_HIST"
    )
    assert (
        physical_document_key(
            DiscoveryObjectType.COLUMN,
            schema_name="DEMIS_OWNER",
            table_name="TB_ADM_HIST",
            column_name="WARD_CD",
        )
        == "COLUMN:DEMIS_OWNER.TB_ADM_HIST.WARD_CD"
    )


def test_deterministic_table_column_document_generation(db_session: Session) -> None:
    revision = _make_revision(db_session)
    first = build_documents_for_revision(revision)
    second = build_documents_for_revision(revision)
    assert len(first) == 5  # 2 tables + 3 columns
    assert [(d.document_key, d.searchable_text, d.document_fingerprint) for d in first] == [
        (d.document_key, d.searchable_text, d.document_fingerprint) for d in second
    ]
    assert all(d.builder_version == BUILDER_VERSION for d in first)
    assert all(d.identity_kind is DiscoveryIdentityKind.PHYSICAL for d in first)

    by_key = {d.document_key: d for d in first}
    table_doc = by_key["TABLE:DEMIS_OWNER.TB_ADM_HIST"]
    assert "Object Type: TABLE" in table_doc.searchable_text
    assert "환자 입원 이력" in table_doc.searchable_text
    assert "ADM_ID" in table_doc.searchable_text
    assert "Primary Keys: ADM_ID" in table_doc.searchable_text
    assert "PK_ADM" in table_doc.searchable_text
    assert "FK_ADM_WARD" in table_doc.searchable_text
    assert "admission" in table_doc.searchable_text

    col_doc = by_key["COLUMN:DEMIS_OWNER.TB_ADM_HIST.WARD_CD"]
    assert "Object Type: COLUMN" in col_doc.searchable_text
    assert "입원 병동 코드" in col_doc.searchable_text
    assert "Data Type: VARCHAR2" in col_doc.searchable_text
    assert "Nullable: true" in col_doc.searchable_text
    assert "FK_ADM_WARD" in col_doc.searchable_text
    assert "DEMIS_OWNER.TB_WARD.WARD_CD" in col_doc.searchable_text


def test_revision_scope_allows_same_physical_keys(
    db_session: Session,
) -> None:
    rev_a = _make_revision(
        db_session,
        fingerprint="fp-dd-a",
        archive_sha256="a" * 64,
    )
    rev_b = _make_revision(
        db_session,
        fingerprint="fp-dd-b",
        archive_sha256="b" * 64,
        payload=_catalog_payload(fingerprint="fp-dd-b"),
    )
    rebuild_for_revision(db_session, rev_a.id)
    rebuild_for_revision(db_session, rev_b.id)
    db_session.flush()

    repo = DataDiscoveryRepository(db_session)
    keys_a = {d.document_key for d in repo.list_for_revision(rev_a.id)}
    keys_b = {d.document_key for d in repo.list_for_revision(rev_b.id)}
    assert "TABLE:DEMIS_OWNER.TB_ADM_HIST" in keys_a
    assert keys_a == keys_b

    for doc in repo.list_for_revision(rev_a.id):
        assert doc.catalog_import_revision_id == rev_a.id
        assert doc.schema_fingerprint == "fp-dd-a"
        assert doc.source_name == "oracle_demis_mock"
    for doc in repo.list_for_revision(rev_b.id):
        assert doc.catalog_import_revision_id == rev_b.id
        assert doc.schema_fingerprint == "fp-dd-b"


def test_rebuild_isolation_does_not_touch_other_revision(
    db_session: Session,
) -> None:
    rev_a = _make_revision(
        db_session,
        fingerprint="fp-dd-a",
        archive_sha256="a" * 64,
    )
    rev_b = _make_revision(
        db_session,
        fingerprint="fp-dd-b",
        archive_sha256="b" * 64,
        payload=_catalog_payload(fingerprint="fp-dd-b"),
    )
    rebuild_for_revision(db_session, rev_a.id)
    rebuild_for_revision(db_session, rev_b.id)
    db_session.flush()

    repo = DataDiscoveryRepository(db_session)
    before_b = {
        (d.document_key, d.document_fingerprint, d.searchable_text)
        for d in repo.list_for_revision(rev_b.id)
    }
    count_b = repo.count_for_revision(rev_b.id)

    # Rebuild A after shrinking its catalog payload — B must stay intact.
    rev_a.tables_json = {
        "tables": [
            {
                "table_key": "DEMIS_OWNER.TB_WARD",
                "schema_name": "DEMIS_OWNER",
                "table_name": "TB_WARD",
                "table_comment": "병동 마스터",
            }
        ]
    }
    rev_a.columns_json = {
        "columns": [
            {
                "table_key": "DEMIS_OWNER.TB_WARD",
                "column_name": "WARD_CD",
                "data_type": "VARCHAR2",
                "primary_key": True,
            }
        ]
    }
    rev_a.relations_json = {"relations": []}
    rev_a.indexes_json = {"indexes": []}
    db_session.flush()

    result = rebuild_for_revision(db_session, rev_a.id)
    db_session.flush()
    assert result.document_count == 2
    assert result.deleted_count >= 1

    after_b = {
        (d.document_key, d.document_fingerprint, d.searchable_text)
        for d in repo.list_for_revision(rev_b.id)
    }
    assert after_b == before_b
    assert repo.count_for_revision(rev_b.id) == count_b
    assert repo.count_for_revision(rev_a.id) == 2


def test_rebuild_for_active_source_uses_pointer(db_session: Session) -> None:
    rev = _make_revision(db_session)
    activate_catalog_revision(db_session, rev.id)
    db_session.flush()
    result = rebuild_for_active_source(db_session, rev.source_name)
    assert result.catalog_import_revision_id == rev.id
    assert result.document_count == 5


def test_rebuild_twice_idempotent_no_duplicates(db_session: Session) -> None:
    rev = _make_revision(db_session)
    first = rebuild_for_revision(db_session, rev.id)
    db_session.flush()
    repo = DataDiscoveryRepository(db_session)
    count_after_first = repo.count_for_revision(rev.id)
    assert count_after_first == first.document_count == 5

    second = rebuild_for_revision(db_session, rev.id)
    db_session.flush()
    docs = repo.list_for_revision(rev.id)
    assert second.document_count == first.document_count
    assert second.deleted_count == 0
    assert repo.count_for_revision(rev.id) == first.document_count
    assert len(docs) == len({d.document_key for d in docs})
    assert {d.document_key for d in docs} == {
        d.document_key for d in build_documents_for_revision(rev)
    }


def test_embedding_model_key_deterministic() -> None:
    base = dict(
        provider="openai-compatible",
        model_name="text-embedding-3-small",
        model_revision="v1",
        dimension=1536,
        normalized=True,
        query_prefix="query: ",
        document_prefix="passage: ",
    )
    key1 = build_embedding_model_key(**base)
    key2 = build_embedding_model_key(**base)
    assert key1 == key2
    assert len(key1) == 64

    changed_model = build_embedding_model_key(**{**base, "model_name": "other-model"})
    changed_dim = build_embedding_model_key(**{**base, "dimension": 768})
    changed_norm = build_embedding_model_key(**{**base, "normalized": False})
    changed_prefix = build_embedding_model_key(**{**base, "query_prefix": None})
    assert len({key1, changed_model, changed_dim, changed_norm, changed_prefix}) == 5

    meta = EmbeddingModelMetadata(**base)
    assert meta.model_key == key1
    # Runtime location fields are not part of the contract.
    assert "endpoint" not in EmbeddingModelMetadata.model_fields
    assert "api_key" not in EmbeddingModelMetadata.model_fields
    assert "path" not in EmbeddingModelMetadata.model_fields


def test_search_request_bounds() -> None:
    DataDiscoverySearchRequest(source_name="oracle_demis_mock", query="admission")
    with pytest.raises(ValidationError):
        DataDiscoverySearchRequest(source_name="oracle_demis_mock", query="   ")
    with pytest.raises(ValidationError):
        DataDiscoverySearchRequest(source_name="oracle_demis_mock", query="")
    with pytest.raises(ValidationError):
        DataDiscoverySearchRequest(
            source_name="oracle_demis_mock", query="x", top_k=0
        )
    with pytest.raises(ValidationError):
        DataDiscoverySearchRequest(
            source_name="oracle_demis_mock", query="x", top_k=51
        )
    with pytest.raises(ValidationError):
        DataDiscoverySearchRequest(
            source_name="oracle_demis_mock", query="x", max_relation_hops=5
        )
    with pytest.raises(ValidationError):
        DataDiscoverySearchRequest(
            source_name="oracle_demis_mock", query="x", max_relation_hops=-1
        )


def test_migration_creates_data_discovery_table(
    test_settings_env: dict[str, str],
) -> None:
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    assert list(script.get_heads()) == [_HEAD]
    rev = script.get_revision(_HEAD)
    assert rev is not None
    assert rev.down_revision == "20261007_hist01"

    engine = get_engine()
    command.upgrade(cfg, "head")
    insp = inspect(engine)
    assert insp.has_table("data_discovery_documents")
    with engine.begin() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == _HEAD

    uqs = {
        uq["name"] for uq in insp.get_unique_constraints("data_discovery_documents")
    }
    assert "uq_data_discovery_documents_revision_document_key" in uqs
    cols = {c["name"] for c in insp.get_columns("data_discovery_documents")}
    assert "active" not in cols
    assert "embedding" not in cols
    assert "vector" not in cols
    # Ensure ORM maps the same table.
    assert DataDiscoveryDocument.__tablename__ == "data_discovery_documents"
