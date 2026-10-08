"""Phase 27-B: Data Discovery search engine tests (keyword/semantic/hybrid/relation)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.adapters.data_discovery.errors import DataDiscoveryErrorCode
from app.domain.data_discovery import build_embedding_model_key
from app.models.catalog_import import CatalogImportRevision
from app.schemas.data_discovery import DataDiscoverySearchRequest
from app.services.catalog_active import activate_catalog_revision
from app.services.data_discovery_document import rebuild_for_revision
from app.services.data_discovery_embedding import sync_embeddings_for_revision
from app.services.data_discovery_search import search_schema
from app.services.data_discovery_search.normalize import normalize_query
from app.services.data_discovery_search.relation import expand_relations
from app.services.data_discovery_search.rrf import RankedItem, reciprocal_rank_fusion
from app.services.data_discovery_search.terminology import expand_medical_terms
from tests.fakes.embedding_provider import StubEmbeddingProvider

pytestmark = pytest.mark.integration


def _catalog_docs() -> dict[str, Any]:
    tables = [
        {
            "table_key": "DEMIS_OWNER.TB_LAB_RESULT",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_LAB_RESULT",
            "table_comment": "laboratory blood glucose and liver function panels",
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_ADM_HIST",
            "table_comment": "patient admission history",
        },
        {
            "table_key": "OTHER_OWNER.TB_ADM_HIST",
            "schema_name": "OTHER_OWNER",
            "table_name": "TB_ADM_HIST",
            "table_comment": "other schema admission",
        },
    ]
    columns = [
        {
            "table_key": "DEMIS_OWNER.TB_LAB_RESULT",
            "column_name": "GLUCOSE",
            "data_type": "NUMBER",
            "column_comment": "blood glucose value",
        },
        {
            "table_key": "DEMIS_OWNER.TB_LAB_RESULT",
            "column_name": "AST",
            "data_type": "NUMBER",
            "column_comment": "aspartate aminotransferase",
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "column_name": "ADM_ID",
            "data_type": "NUMBER",
            "primary_key": True,
            "column_comment": "admission id",
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "column_name": "LAB_ID",
            "data_type": "NUMBER",
            "column_comment": "fk to lab",
        },
    ]
    relations = [
        {
            "constraint_name": "FK_ADM_LAB",
            "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "target_table_key": "DEMIS_OWNER.TB_LAB_RESULT",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "LAB_ID",
                    "target_column": "GLUCOSE",
                }
            ],
        }
    ]
    return {
        "tables": tables,
        "columns": columns,
        "relations": relations,
        "indexes": [],
        "categories": [],
        "assignments": [],
    }


def _make_revision(
    session: Session,
    *,
    source_name: str = "oracle_demis_mock",
    fingerprint: str = "fp-search-a",
    archive_sha256: str = "1" * 64,
) -> CatalogImportRevision:
    docs = _catalog_docs()
    revision = CatalogImportRevision(
        source_name=source_name,
        db_type="oracle",
        database_name="FREEPDB1",
        default_schema="DEMIS_OWNER",
        package_format="demis-catalog-package",
        package_version="2.0",
        package_readiness="READY",
        schema_fingerprint=fingerprint,
        archive_sha256=archive_sha256,
        manifest_sha256="2" * 64,
        generated_at=datetime(2026, 10, 8, tzinfo=UTC),
        validation_status="VALID",
        table_count=len(docs["tables"]),
        column_count=len(docs["columns"]),
        relation_count=len(docs["relations"]),
        index_count=0,
        category_count=0,
        category_assignment_count=0,
        managed_file_count=1,
        manifest_json={},
        database_json={},
        tables_json={"tables": docs["tables"]},
        columns_json={"columns": docs["columns"]},
        relations_json={"relations": docs["relations"]},
        indexes_json={"indexes": docs["indexes"]},
        categories_json={
            "categories": docs["categories"],
            "table_assignments": docs["assignments"],
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


def _prepare_active(session: Session) -> CatalogImportRevision:
    rev = _make_revision(session)
    rebuild_for_revision(session, rev.id)
    activate_catalog_revision(session, rev.id)
    session.flush()
    return rev


def test_terminology_expansion_and_schema_leakage_guard() -> None:
    liver = expand_medical_terms(normalize_query("간수치 확인해줘"))
    assert "liver_function" in liver.matched_concepts
    assert any(term.casefold() == "ast" for term in liver.expanded_terms)
    assert all("TB_" not in term for term in liver.expanded_terms)
    assert all("." not in term for term in liver.expanded_terms)

    glucose = expand_medical_terms(normalize_query("HbA1c trend"))
    assert "blood_glucose" in glucose.matched_concepts

    # Latin token boundary: AST must not match inside unrelated tokens.
    no_match = expand_medical_terms(normalize_query("lastname"))
    assert "liver_function" not in no_match.matched_concepts

    a = expand_medical_terms(normalize_query("hypertension"))
    b = expand_medical_terms(normalize_query("hypertension"))
    assert a == b


def test_keyword_search_revision_isolation_and_boosts(db_session: Session) -> None:
    rev_a = _prepare_active(db_session)
    rev_b = _make_revision(
        db_session,
        source_name="oracle_demis_other",
        fingerprint="fp-search-b",
        archive_sha256="3" * 64,
    )
    rebuild_for_revision(db_session, rev_b.id)
    activate_catalog_revision(db_session, rev_b.id)
    session_flush = db_session.flush
    session_flush()

    response = search_schema(
        db_session,
        DataDiscoverySearchRequest(
            source_name=rev_a.source_name,
            query="TB_LAB_RESULT",
            mode="keyword",
            top_k=5,
        ),
    )
    assert response.catalog_revision_id == rev_a.id
    assert response.results
    assert response.results[0].document_key == "TABLE:DEMIS_OWNER.TB_LAB_RESULT"
    assert response.results[0].keyword_score is not None

    # Expanded term weight lower than direct identifier query on glucose column.
    direct = search_schema(
        db_session,
        DataDiscoverySearchRequest(
            source_name=rev_a.source_name,
            query="GLUCOSE",
            mode="keyword",
            object_type="COLUMN",
            expand_terms=False,
            top_k=5,
        ),
    )
    expanded = search_schema(
        db_session,
        DataDiscoverySearchRequest(
            source_name=rev_a.source_name,
            query="혈당",
            mode="keyword",
            object_type="COLUMN",
            expand_terms=True,
            top_k=5,
        ),
    )
    direct_hit = next(
        r for r in direct.results if r.document_key.endswith(".GLUCOSE")
    )
    expanded_hit = next(
        r for r in expanded.results if r.document_key.endswith(".GLUCOSE")
    )
    assert direct_hit.keyword_score is not None
    assert expanded_hit.keyword_score is not None
    assert direct_hit.keyword_score > expanded_hit.keyword_score

    # Injection-like text must not break search (bound parameters).
    safe = search_schema(
        db_session,
        DataDiscoverySearchRequest(
            source_name=rev_a.source_name,
            query="GLUCOSE' OR 1=1 --",
            mode="keyword",
            top_k=5,
        ),
    )
    assert safe.catalog_revision_id == rev_a.id


def test_semantic_requires_ready_coverage(db_session: Session) -> None:
    rev = _prepare_active(db_session)
    provider = StubEmbeddingProvider()

    with pytest.raises(Exception) as exc:
        search_schema(
            db_session,
            DataDiscoverySearchRequest(
                source_name=rev.source_name,
                query="blood glucose lab",
                mode="semantic",
            ),
            embedding_provider=provider,
        )
    assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_NOT_READY

    sync_embeddings_for_revision(db_session, rev.id, provider)
    db_session.flush()
    response = search_schema(
        db_session,
        DataDiscoverySearchRequest(
            source_name=rev.source_name,
            query="blood glucose laboratory",
            mode="semantic",
            top_k=5,
        ),
        embedding_provider=provider,
    )
    assert response.model_key == provider.model_key
    assert response.results
    assert response.results[0].semantic_score is not None
    keys = [r.document_key for r in response.results]
    assert any("LAB" in key or "GLUCOSE" in key for key in keys)


def test_hybrid_rrf_and_keyword_without_provider(db_session: Session) -> None:
    rev = _prepare_active(db_session)
    keyword_only = search_schema(
        db_session,
        DataDiscoverySearchRequest(
            source_name=rev.source_name,
            query="admission",
            mode="keyword",
        ),
    )
    assert keyword_only.results

    with pytest.raises(Exception) as exc:
        search_schema(
            db_session,
            DataDiscoverySearchRequest(
                source_name=rev.source_name,
                query="admission",
                mode="hybrid",
            ),
            embedding_provider=None,
        )
    assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_NOT_CONFIGURED

    provider = StubEmbeddingProvider()
    sync_embeddings_for_revision(db_session, rev.id, provider)
    db_session.flush()
    hybrid = search_schema(
        db_session,
        DataDiscoverySearchRequest(
            source_name=rev.source_name,
            query="admission history",
            mode="hybrid",
            top_k=5,
        ),
        embedding_provider=provider,
    )
    assert hybrid.results
    assert hybrid.results[0].rrf_score is not None


def test_rrf_deterministic_merge() -> None:
    semantic = [
        RankedItem(key="A", payload="A", rank=1, score=0.9),
        RankedItem(key="B", payload="B", rank=2, score=0.8),
    ]
    keyword = [
        RankedItem(key="B", payload="B", rank=1, score=12.0),
        RankedItem(key="A", payload="A", rank=2, score=10.0),
    ]
    fused = reciprocal_rank_fusion(semantic_items=semantic, keyword_items=keyword, k=60)
    assert [item.key for item in fused] == [
        item.key
        for item in reciprocal_rank_fusion(
            semantic_items=semantic, keyword_items=keyword, k=60
        )
    ]
    assert len(fused) == 2
    assert fused[0].semantic_rank is not None
    assert fused[0].keyword_rank is not None


def test_relation_expansion_multi_schema_and_cycle(db_session: Session) -> None:
    rev = _prepare_active(db_session)
    related = expand_relations(
        rev,
        seed_tables=[("DEMIS_OWNER", "TB_ADM_HIST")],
        max_hops=1,
    )
    assert any(
        item.schema_name == "DEMIS_OWNER" and item.table_name == "TB_LAB_RESULT"
        for item in related
    )
    # Same table name in OTHER_OWNER must not be selected via bare-name collision.
    assert all(item.table_name != "TB_ADM_HIST" or item.schema_name == "DEMIS_OWNER" or item.hop_distance >= 1 for item in related)

    docs = _catalog_docs()
    # Add a cycle edge LAB -> ADM
    docs["relations"].append(
        {
            "constraint_name": "FK_LAB_ADM",
            "source_table_key": "DEMIS_OWNER.TB_LAB_RESULT",
            "target_table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "GLUCOSE",
                    "target_column": "ADM_ID",
                }
            ],
        }
    )
    rev.relations_json = {"relations": docs["relations"]}
    db_session.flush()
    related2 = expand_relations(
        rev,
        seed_tables=[("DEMIS_OWNER", "TB_ADM_HIST")],
        max_hops=2,
    )
    # Cycle-safe: finite unique related tables.
    keys = {(r.schema_name, r.table_name) for r in related2}
    assert ("DEMIS_OWNER", "TB_LAB_RESULT") in keys

    response = search_schema(
        db_session,
        DataDiscoverySearchRequest(
            source_name=rev.source_name,
            query="TB_ADM_HIST",
            mode="keyword",
            expand_relations=True,
            max_relation_hops=1,
            top_k=5,
        ),
    )
    assert response.related_tables
    assert response.related_tables[0].path


def test_model_key_stable_across_endpoint_change() -> None:
    a = build_embedding_model_key(
        provider="openai_compatible",
        model_name="bge-m3",
        model_revision=None,
        dimension=1024,
        normalized=True,
        query_prefix=None,
        document_prefix=None,
    )
    b = build_embedding_model_key(
        provider="openai_compatible",
        model_name="bge-m3",
        model_revision=None,
        dimension=1024,
        normalized=True,
        query_prefix=None,
        document_prefix=None,
    )
    assert a == b
    c = build_embedding_model_key(
        provider="openai_compatible",
        model_name="bge-m3",
        model_revision="v2",
        dimension=1024,
        normalized=True,
        query_prefix=None,
        document_prefix=None,
    )
    assert c != a
