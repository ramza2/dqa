"""S-06-B synthetic multi-schema/medical-term Gold Search on disposable pgvector.

The imported S-06-A factory refuses every non-disposable DB target and the
module skips unless DQA_S06A_ISOLATED_PG=1. No db_session/TRUNCATE, Oracle,
clinical rows, ModelOps network calls or real medical retrieval quality claims.
"""
from __future__ import annotations

import json
from math import log2

import pytest

from app.schemas.data_discovery import DataDiscoverySearchRequest
from app.services.catalog_active import activate_catalog_revision
from app.services.data_discovery_document import rebuild_for_revision
from app.services.data_discovery_embedding import sync_embeddings_for_revision
from app.services.data_discovery_search import search_schema
from tests.fakes.embedding_provider import StubEmbeddingProvider
from tests.test_data_discovery_search import _make_revision
from tests.test_s06a_disposable_pg_gold_search import factory

SOURCE = "s06b_gold_primary"
OTHER_SOURCE = "s06b_gold_other"

# Deliberately small, non-clinical metadata with same table name in 2 schemas.
# These are hypothetical *schema labels*, not actual hospital data or tables.
TABLES = (
    ("DEMIS_OWNER", "TB_LAB_RESULT", "laboratory glucose AST hepatic panel"),
    ("DEMIS_OWNER", "TB_RENAL", "renal kidney creatinine laboratory"),
    ("DEMIS_OWNER", "TB_MED_ORDERS", "medication prescription pharmacy"),
    ("DEMIS_OWNER", "TB_CLINICAL_NOTE", "discharge summary note"),
    ("OTHER_OWNER", "TB_LAB_RESULT", "archive indexing audit only"),
    ("OTHER_OWNER", "TB_MED_ORDERS", "archive indexing audit only"),
)
COLUMNS = (
    ("DEMIS_OWNER", "TB_LAB_RESULT", "GLUCOSE", "blood glucose analysis"),
    ("DEMIS_OWNER", "TB_LAB_RESULT", "AST", "hepatic liver function"),
    ("DEMIS_OWNER", "TB_RENAL", "CREATININE", "renal kidney marker"),
    ("DEMIS_OWNER", "TB_MED_ORDERS", "MEDICATION_ID", "prescription identifier"),
)
SRC_PREFIX = "DEMIS_OWNER"

# Human-curated *synthetic* relevance judgements; they do not certify real
# BGE-M3 embeddings or clinical retrieval/decision safety.
GOLD_QUERIES = (
    {"query": "혈당", "concept": "blood_glucose",
     "type": "COLUMN", "gold": "COLUMN:DEMIS_OWNER.TB_LAB_RESULT.GLUCOSE", "k": 5},
    {"query": "간수치", "concept": "liver_function",
     "type": "COLUMN", "gold": "COLUMN:DEMIS_OWNER.TB_LAB_RESULT.AST", "k": 5},
    {"query": "신기능", "concept": "renal_function",
     "type": "COLUMN", "gold": "COLUMN:DEMIS_OWNER.TB_RENAL.CREATININE", "k": 5},
    {"query": "투약", "concept": "medication",
     "type": "TABLE", "gold": "TABLE:DEMIS_OWNER.TB_MED_ORDERS", "k": 5},
    {"query": "퇴원요약", "concept": "discharge_summary",
     "type": "TABLE", "gold": "TABLE:DEMIS_OWNER.TB_CLINICAL_NOTE", "k": 5},
)


def _metrics(keys: list[str], relevant: set[str], k: int) -> dict[str, float]:
    assert relevant and k > 0, "Gold relevance labels and cutoff required"
    ranks = [index for index, key in enumerate(keys[:k], 1) if key in relevant]
    hits = len(set(keys[:k]) & relevant)
    dcg = sum(1.0 / log2(rank + 1) for rank in ranks)
    ideal = sum(1.0 / log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return {
        "recall_at_k": hits / len(relevant),
        "precision_at_k": hits / k,
        "mrr_at_k": 1.0 / min(ranks) if ranks else 0.0,
        "ndcg_at_k": dcg / ideal if ideal else 0.0,
    }


def _key(schema, table, column=None):
    return f"{'COLUMN' if column else 'TABLE'}:{schema}.{table}" + (
        f".{column}" if column else ""
    )


def _query(db, query, mode="keyword", *, source=SOURCE, kind=None, expand=True,
           top_k=10, provider=None):
    return search_schema(
        db,
        DataDiscoverySearchRequest(
            source_name=source, query=query, mode=mode, top_k=top_k,
            object_type=kind, expand_terms=expand, expand_relations=False,
        ),
        embedding_provider=provider,
    )


def _assert_provenance(response, source, revision):
    assert (response.source_name, response.catalog_revision_id,
            response.schema_fingerprint) == (
        source, revision.id, revision.schema_fingerprint
    )
    for rank, hit in enumerate(response.results, 1):
        assert hit.rank == rank
        assert (
            hit.identity.source_name, hit.identity.catalog_revision_id,
            hit.identity.schema_fingerprint,
        ) == (source, revision.id, revision.schema_fingerprint)
        assert hit.document_key == _key(
            hit.identity.schema_name, hit.identity.table_name,
            hit.identity.column_name,
        )
        assert hit.evidence
        assert hit.evidence_snippet is not None


def test_s06b_metric_arithmetic_relevant_and_missing():
    assert _metrics(["A", "B", "C"], {"A", "C"}, 3) == {
        "recall_at_k": 1.0,
        "precision_at_k": 2 / 3,
        "mrr_at_k": 1.0,
        "ndcg_at_k": 1.0 / (1.0 + 1.0 / log2(3))
        * (1.0 + 1.0 / log2(4)),
    }
    missing = _metrics(["X", "Y"], {"A"}, 2)
    assert all(value == 0.0 for value in missing.values())
    with pytest.raises(AssertionError):
        _metrics(["A"], set(), 5)


def test_s06b_multischema_gold_terms_and_provenance(factory):
    provider = StubEmbeddingProvider(model_name="s06b-gold-hash-stub")
    with factory() as db:
        rev = _make_revision(
            db, source_name=SOURCE,
            fingerprint="s06b-synthetic-revision-a1", archive_sha256="d" * 64,
        )
        rev.tables_json = {"tables": [
            {"table_key": f"{schema}.{table}", "schema_name": schema,
             "table_name": table, "table_comment": comment}
            for schema, table, comment in TABLES
        ]}
        rev.columns_json = {"columns": [
            {"table_key": f"{schema}.{table}", "column_name": col,
             "data_type": "VARCHAR2", "column_comment": comment}
            for schema, table, col, comment in COLUMNS
        ]}
        rev.relations_json = {"relations": [
            {
                "constraint_name": "FK_LAB_RENAL_COMPOSITE",
                "source_table_key": "DEMIS_OWNER.TB_LAB_RESULT",
                "target_table_key": "DEMIS_OWNER.TB_RENAL",
                "column_mapping": [
                    {"ordinal_position": 2, "source_column": "AST",
                     "target_column": "CREATININE"},
                    {"ordinal_position": 1, "source_column": "GLUCOSE",
                     "target_column": "CREATININE"},
                ],
            },
        ]}
        rev.indexes_json = {"indexes": []}
        rev.table_count = len(TABLES)
        rev.column_count = len(COLUMNS)
        rev.relation_count = 1
        built = rebuild_for_revision(db, rev.id)
        assert built.document_count == len(TABLES) + len(COLUMNS)
        synced = sync_embeddings_for_revision(db, rev.id, provider)
        assert synced.document_count == built.document_count
        assert activate_catalog_revision(db, rev.id).changed

        other = _make_revision(
            db, source_name=OTHER_SOURCE,
            fingerprint="s06b-synthetic-other", archive_sha256="e" * 64,
        )
        assert rebuild_for_revision(db, other.id).document_count > 0
        sync_embeddings_for_revision(db, other.id, provider)
        assert activate_catalog_revision(db, other.id).changed
        db.commit()

    with factory() as db:
        # A fully qualified identifier must rank before the equal bare table
        # name in OTHER_OWNER within the same active Source.
        exact_cases = (
            ("DEMIS_OWNER.TB_LAB_RESULT", "TABLE",
             "TABLE:DEMIS_OWNER.TB_LAB_RESULT"),
            ("DEMIS_OWNER.TB_LAB_RESULT.GLUCOSE", "COLUMN",
             "COLUMN:DEMIS_OWNER.TB_LAB_RESULT.GLUCOSE"),
        )
        metrics = []
        for query, kind, gold in exact_cases:
            res = _query(db, query, kind=kind, expand=False, top_k=5)
            _assert_provenance(res, SOURCE, rev)
            keys = [x.document_key for x in res.results]
            assert keys[0] == gold
            assert _metrics(keys, {gold}, 1)["mrr_at_k"] == 1.0
            assert "exact_" in " ".join(res.results[0].evidence)

        # Dictionary expansion is inspected independently from retriever
        # relevance so "no physical schema identifiers" remains a guard.
        for item in GOLD_QUERIES:
            res = _query(
                db, item["query"], kind=item["type"],
                expand=True, top_k=item["k"],
            )
            _assert_provenance(res, SOURCE, rev)
            assert item["concept"] in res.matched_concepts
            assert all(not token.upper().startswith("TB_") for token in res.expanded_terms)
            score = _metrics(
                [x.document_key for x in res.results], {item["gold"]}, item["k"],
            )
            assert score["recall_at_k"] == 1.0, (item["query"], score)
            assert score["mrr_at_k"] > 0.0
            metrics.append({
                "query": item["query"], "k": item["k"], **score,
            })
            # Without term expansion none of the synthetic English-only
            # documents should match these Korean query strings.
            no_expansion = _query(
                db, item["query"], kind=item["type"],
                expand=False, top_k=item["k"],
            )
            assert not no_expansion.results

        assert all(_query(db, "zzxqvnohits98765", expand=True).results == []
                   for _ in range(2))
        # The fixture's Source B intentionally shares physical document keys,
        # but search identities must never cross the active Source boundary.
        other_res = _query(
            db, "TB_LAB_RESULT", source=OTHER_SOURCE,
            expand=False, top_k=10,
        )
        _assert_provenance(other_res, OTHER_SOURCE, other)
        assert {x.identity.source_name for x in other_res.results} == {OTHER_SOURCE}

        for mode in ("semantic", "hybrid"):
            res = _query(
                db, "혈당", mode, kind="COLUMN",
                provider=provider, top_k=20,
            )
            _assert_provenance(res, SOURCE, rev)
            assert res.model_key == provider.model_key
            assert len({x.document_key for x in res.results}) == len(res.results)
            # Hash-derived embeddings cannot establish real semantic rank;
            # only per-Source/model isolation and bounded results are asserted.
            metrics.append({
                "mode": mode, "query": "혈당", "returned": len(res.results),
                "model_key_matches": res.model_key == provider.model_key,
            })

        print("S06B_SYNTHETIC_GOLD_METRICS " +
              json.dumps(metrics, sort_keys=True, ensure_ascii=False))
