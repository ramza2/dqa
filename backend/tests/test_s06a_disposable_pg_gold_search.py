"""S-06-A Gold Search: only the dedicated, disposable loopback PostgreSQL.

No db_session fixture (it TRUNCATEs), Oracle, DEMIS, production DB, clinical
records, LLM, network embedding model, or real-DEMIS parity claims. ORM READY
rows below are synthetic search fixtures, not approval/preflight evidence.
"""
from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode
from app.core.config import get_settings
from app.models.data_discovery import DataDiscoveryDocument
from app.schemas.data_discovery import DataDiscoverySearchRequest
from app.services.catalog_active import activate_catalog_revision, get_active_catalog
from app.services.data_discovery_document import rebuild_for_revision
from app.services.data_discovery_embedding import sync_embeddings_for_revision
from app.services.data_discovery_search import search_schema
from app.services.data_discovery_search.relation import expand_relations
from tests.fakes.embedding_provider import StubEmbeddingProvider
from tests.test_data_discovery_search import _make_revision

pytestmark = pytest.mark.integration

if os.environ.get("DQA_S06A_ISOLATED_PG") != "1":
    pytest.skip("S-06-A requires a dedicated disposable PostgreSQL", allow_module_level=True)

SOURCE_A = "s06a_gold_primary"
SOURCE_B = "s06a_gold_other"
FP_A1 = "s06a-gold-a1"
FP_A2 = "s06a-gold-a2"
FP_B = "s06a-gold-b1"

# Curated *synthetic* Gold Set. Recall@k is exact-key inclusion, not BGE-M3
# clinical retrieval quality. Only keyword queries have strict relevance labels.
KEYWORD_GOLD = (
    ("TB_LAB_RESULT", "TABLE", "TABLE:DEMIS_OWNER.TB_LAB_RESULT", 5),
    ("GLUCOSE", "COLUMN", "COLUMN:DEMIS_OWNER.TB_LAB_RESULT.GLUCOSE", 5),
)


@pytest.fixture(scope="module")
def factory():
    cfg = get_settings()
    assert (
        cfg.app_env == "test"
        and cfg.dqa_db_host == "127.0.0.1"
        and cfg.dqa_db_port == 55442
        and cfg.dqa_db_name == "dqa_s06a_disposable"
        and cfg.dqa_db_user == "dqa_s06a_user"
    ), "S06A_REFUSED: target is not dedicated disposable PostgreSQL"
    engine = create_engine(
        cfg.sqlalchemy_database_url, pool_pre_ping=True, future=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
    )
    try:
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT current_database()")) == "dqa_s06a_disposable"
            assert conn.scalar(text("SELECT current_user")) == "dqa_s06a_user"
            for name in (
                "catalog_import_revisions", "catalog_active_revisions",
                "data_discovery_documents", "data_discovery_embeddings",
            ):
                assert conn.scalar(
                    text("SELECT to_regclass(:table)"), {"table": f"public.{name}"}
                ) is not None
        yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    finally:
        engine.dispose()


def _search(db, source, query, mode, *, provider=None, top_k=10, object_type=None,
            expand_relations=False):
    return search_schema(
        db,
        DataDiscoverySearchRequest(
            source_name=source,
            query=query,
            mode=mode,
            object_type=object_type,
            top_k=top_k,
            expand_terms=False,
            expand_relations=expand_relations,
            max_relation_hops=1 if expand_relations else 0,
        ),
        embedding_provider=provider,
    )


def _assert_provenance(response, *, source, revision):
    assert response.source_name == source
    assert response.catalog_revision_id == revision.id
    assert response.schema_fingerprint == revision.schema_fingerprint
    for item in response.results:
        identity = item.identity
        assert (
            identity.source_name,
            identity.catalog_revision_id,
            identity.schema_fingerprint,
        ) == (source, revision.id, revision.schema_fingerprint)
        assert item.document_key.startswith(("TABLE:", "COLUMN:"))
        assert item.rank >= 1


def _recall_at_k(response, expected_keys, k):
    actual = {item.document_key for item in response.results[:k]}
    return len(actual & expected_keys) / len(expected_keys)


def test_gold_keyword_composite_relation_provenance_and_active_switch(factory):
    provider = StubEmbeddingProvider(model_name="s06a-deterministic-only")

    # First active Revision for Source A, and an unrelated Source B with
    # overlapping object keys. Neither source can read the other's revision.
    with factory() as db:
        a1 = _make_revision(
            db, source_name=SOURCE_A, fingerprint=FP_A1, archive_sha256="a" * 64,
        )
        a1.relations_json = {
            "relations": [{
                "constraint_name": "FK_ADM_LAB_COMPOSITE",
                "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "target_table_key": "DEMIS_OWNER.TB_LAB_RESULT",
                "column_mapping": [
                    {"ordinal_position": 1, "source_column": "LAB_ID", "target_column": "GLUCOSE"},
                    {"ordinal_position": 2, "source_column": "ADM_ID", "target_column": "AST"},
                ],
            }],
        }
        b1 = _make_revision(
            db, source_name=SOURCE_B, fingerprint=FP_B, archive_sha256="b" * 64,
        )
        for rev in (a1, b1):
            rebuilt = rebuild_for_revision(db, rev.id)
            assert rebuilt.document_count > 0
            sync = sync_embeddings_for_revision(db, rev.id, provider)
            assert sync.document_count == rebuilt.document_count
            activated = activate_catalog_revision(db, rev.id)
            assert activated.changed
        db.commit()

    with factory() as db:
        report = []
        for query, object_type, expected, top_k in KEYWORD_GOLD:
            response = _search(
                db, SOURCE_A, query, "keyword", top_k=top_k, object_type=object_type,
            )
            _assert_provenance(response, source=SOURCE_A, revision=a1)
            recall = _recall_at_k(response, {expected}, top_k)
            report.append({"mode": "keyword", "query": query, "k": top_k, "recall": recall})
            assert recall == 1.0, f"Gold result missing for {query}"

        relations = expand_relations(
            a1, seed_tables=[("DEMIS_OWNER", "TB_ADM_HIST")], max_hops=1,
        )
        related = next(x for x in relations if x.table_name == "TB_LAB_RESULT")
        assert related.hop_distance == 1
        assert len(related.path) == 1
        assert related.path[0].constraint_name == "FK_ADM_LAB_COMPOSITE"
        assert related.path[0].from_columns == ("LAB_ID", "ADM_ID")
        assert related.path[0].to_columns == ("GLUCOSE", "AST")
        assert all(x.schema_name != "OTHER_OWNER" for x in relations)

        relation_search = _search(
            db, SOURCE_A, "TB_ADM_HIST", "keyword",
            top_k=10, object_type="TABLE", expand_relations=True,
        )
        _assert_provenance(relation_search, source=SOURCE_A, revision=a1)
        assert any(x.table_name == "TB_LAB_RESULT" for x in relation_search.related_tables)

        for mode in ("semantic", "hybrid"):
            response = _search(
                db, SOURCE_A, "TB_LAB_RESULT", mode, provider=provider, top_k=50,
            )
            _assert_provenance(response, source=SOURCE_A, revision=a1)
            assert response.model_key == provider.model_key
            assert response.results
            assert all(x.evidence for x in response.results)
            # Diagnostic only: hash-derived vectors are NOT relevance labels.
            report.append({"mode": mode, "query": "TB_LAB_RESULT",
                           "k": 50, "returned": len(response.results)})
        other = _search(db, SOURCE_B, "TB_LAB_RESULT", "keyword")
        _assert_provenance(other, source=SOURCE_B, revision=b1)
        assert db.scalars(
            select(DataDiscoveryDocument)
            .where(DataDiscoveryDocument.catalog_import_revision_id == a1.id)
        ).first() is not None
        print("S06A_SYNTHETIC_GOLD_METRICS " + json.dumps(report, sort_keys=True))

    # Switch Source A only: old Revision A1 remains immutable/history, but
    # new Active A2 has only TB_V2_ONLY and NO embeddings until explicitly synced.
    with factory() as db:
        a2 = _make_revision(
            db, source_name=SOURCE_A, fingerprint=FP_A2, archive_sha256="c" * 64,
        )
        a2.tables_json = {"tables": [{
            "table_key": "DEMIS_OWNER.TB_V2_ONLY",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_V2_ONLY",
            "table_comment": "synthetic revision-only table",
        }]}
        a2.columns_json = {"columns": []}
        a2.relations_json = {"relations": []}
        a2.indexes_json = {"indexes": []}
        rebuilt = rebuild_for_revision(db, a2.id)
        assert rebuilt.document_count == 1
        changed = activate_catalog_revision(db, a2.id)
        assert changed.changed and changed.previous_revision_id == a1.id
        db.commit()

    with factory() as db:
        old_search = _search(db, SOURCE_A, "TB_LAB_RESULT", "keyword")
        _assert_provenance(old_search, source=SOURCE_A, revision=a2)
        assert old_search.results == []

        current = _search(db, SOURCE_A, "TB_V2_ONLY", "keyword")
        _assert_provenance(current, source=SOURCE_A, revision=a2)
        assert _recall_at_k(current, {"TABLE:DEMIS_OWNER.TB_V2_ONLY"}, 5) == 1.0

        with pytest.raises(DataDiscoveryError) as exc:
            _search(db, SOURCE_A, "TB_V2_ONLY", "semantic", provider=provider)
        assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_NOT_READY

        assert get_active_catalog(db, SOURCE_A).revision_id == a2.id
        assert get_active_catalog(db, SOURCE_B).revision_id == b1.id
        other = _search(db, SOURCE_B, "TB_LAB_RESULT", "keyword")
        _assert_provenance(other, source=SOURCE_B, revision=b1)

        sync_embeddings_for_revision(db, a2.id, provider)
        db.commit()

    with factory() as db:
        for mode in ("semantic", "hybrid"):
            current = _search(
                db, SOURCE_A, "TB_V2_ONLY", mode, provider=provider, top_k=10,
            )
            _assert_provenance(current, source=SOURCE_A, revision=a2)
            assert current.model_key == provider.model_key
            assert {r.document_key for r in current.results} == {
                "TABLE:DEMIS_OWNER.TB_V2_ONLY"
            }
        remaining_old = db.scalars(select(DataDiscoveryDocument).where(
            DataDiscoveryDocument.catalog_import_revision_id == a1.id,
        )).all()
        assert remaining_old
        assert all(doc.catalog_import_revision_id == a1.id for doc in remaining_old)
