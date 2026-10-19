"""S-06-F: imported Oracle WARNING cannot become active search provenance.

Only the opt-in disposable PostgreSQL from S-06-B (loopback 127.0.0.1:55442).
No production DB, db_session fixture, real Oracle/DEMIS, clinical rows, remote
LLM/embedding, independent READY issuer or site approval. READY test package
is a fabricated isolated fixture, not trusted external evidence.
"""
from __future__ import annotations

from sqlalchemy import select

from app.adapters.catalog.activation_errors import (
    CatalogActivationError, CatalogActivationErrorCode,
)
from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.models.catalog_active import CatalogActivationEvent
from app.models.data_discovery import DataDiscoveryDocument
from app.schemas.data_discovery import DataDiscoverySearchRequest
from app.services.catalog_active import activate_catalog_revision, get_active_catalog
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.catalog_query import list_tables
from app.services.data_discovery_document import rebuild_for_revision
from app.services.data_discovery_embedding import sync_embeddings_for_revision
from app.services.data_discovery_search import search_schema
from app.services.schema_catalog_candidate import build_catalog_v2_candidate
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE, build_core_documents, build_package_zip,
)
from tests.fakes.embedding_provider import StubEmbeddingProvider
from tests.test_s06a_disposable_pg_gold_search import factory
from tests.test_s06c_oracle_inspector_candidate_chain import TIMESTAMP, _inspect

# Unique sources do not interfere with existing S-06-A/B fixtures sharing the
# same disposable PostgreSQL and prevent cross-test SHA de-duplication.
NO_ACTIVE_SOURCE = "s06f_warning_without_pointer"
ACTIVE_SOURCE = "s06f_ready_pointer_remains"
READY_TABLE = "TB_S06F_READY_ONLY"
WARNING_TABLE = "TB_VISIT"


def _warning_zip(source: str) -> bytes:
    return build_catalog_v2_candidate(
        _inspect(), source_name=source, generated_at=TIMESTAMP,
    )


def _synthetic_ready_zip(source: str) -> bytes:
    # WARNING candidates cannot be upgraded to READY by DQA. This separate,
    # explicitly synthetic fixture exercises the existing READY-only pointer.
    src = {**DEFAULT_SOURCE, "source_name": source}
    fp = "s06f-fixture-ready-only-not-dba-attested"
    docs = build_core_documents(
        source=src,
        fingerprint=fp,
        tables=[{
            "table_key": f"DEMIS_OWNER.{READY_TABLE}",
            "schema_name": "DEMIS_OWNER",
            "table_name": READY_TABLE,
            "table_comment": "safe synthetic ready-only catalog",
        }],
        columns=[{
            "table_key": f"DEMIS_OWNER.{READY_TABLE}",
            "column_name": "ID",
            "ordinal_position": 1,
            "data_type": "NUMBER",
            "nullable": False,
            "column_comment": "synthetic identifier",
            "primary_key": True,
            "unique": True,
        }],
        relations=[], indexes=[], categories=[],
    )
    return build_package_zip(
        package_readiness="READY", source=src, fingerprint=fp, files=docs,
    )


def _query(db, source: str, query: str, mode: str, *, provider=None):
    return search_schema(
        db,
        DataDiscoverySearchRequest(
            source_name=source, query=query, mode=mode, top_k=10,
            expand_terms=False, expand_relations=True, max_relation_hops=1,
        ),
        embedding_provider=provider,
    )


def test_warning_import_index_without_active_pointer_is_not_searchable(factory):
    source = NO_ACTIVE_SOURCE
    provider = StubEmbeddingProvider(model_name="s06f-isolated-stub")
    with factory() as db:
        warning, created = import_catalog_package_bytes(_warning_zip(source), db)
        assert created and warning.package_readiness == "WARNING"
        assert rebuild_for_revision(db, warning.id).document_count == 6
        assert sync_embeddings_for_revision(db, warning.id, provider).embedded_count == 6
        with __import__("pytest").raises(CatalogActivationError) as caught:
            activate_catalog_revision(db, warning.id)
        assert caught.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
        db.commit()

    with factory() as db:
        assert db.scalar(select(DataDiscoveryDocument.id).where(
            DataDiscoveryDocument.catalog_import_revision_id == warning.id
        ).limit(1)) is not None
        with __import__("pytest").raises(CatalogQueryError) as caught:
            _query(db, source, WARNING_TABLE, "keyword")
        assert caught.value.code == CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND
        assert db.scalars(select(CatalogActivationEvent).where(
            CatalogActivationEvent.source_name == source
        )).all() == []


def test_ready_search_and_provenance_unchanged_after_warning_index(factory):
    source = ACTIVE_SOURCE
    provider = StubEmbeddingProvider(model_name="s06f-isolated-stub")
    with factory() as db:
        ready, created = import_catalog_package_bytes(_synthetic_ready_zip(source), db)
        assert created and ready.package_readiness == "READY"
        assert rebuild_for_revision(db, ready.id).document_count == 2
        assert sync_embeddings_for_revision(db, ready.id, provider).embedded_count == 2
        assert activate_catalog_revision(db, ready.id).changed
        db.commit()

    with factory() as db:
        before = _query(db, source, READY_TABLE, "keyword")
        assert before.catalog_revision_id == ready.id
        assert [result.document_key for result in before.results] == [
            f"TABLE:DEMIS_OWNER.{READY_TABLE}",
        ]
        active_before = get_active_catalog(db, source)
        assert active_before.revision_id == ready.id
        assert active_before.package_readiness == "READY"
        event_ids_before = db.scalars(
            select(CatalogActivationEvent.id).where(
                CatalogActivationEvent.source_name == source
            ).order_by(CatalogActivationEvent.id)
        ).all()

        warning, created = import_catalog_package_bytes(_warning_zip(source), db)
        assert created and warning.package_readiness == "WARNING"
        assert warning.schema_fingerprint != ready.schema_fingerprint
        assert rebuild_for_revision(db, warning.id).document_count == 6
        assert sync_embeddings_for_revision(db, warning.id, provider).embedded_count == 6
        with __import__("pytest").raises(CatalogActivationError) as caught:
            activate_catalog_revision(db, warning.id)
        assert caught.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
        db.commit()

    with factory() as db:
        active_after = get_active_catalog(db, source)
        assert active_after.revision_id == ready.id
        assert active_after.schema_fingerprint == ready.schema_fingerprint
        assert active_after.package_readiness == "READY"
        assert db.scalars(
            select(CatalogActivationEvent.id).where(
                CatalogActivationEvent.source_name == source
            ).order_by(CatalogActivationEvent.id)
        ).all() == event_ids_before
        assert [x.name for x in list_tables(db, source)[1].items] == [READY_TABLE]

        no_warning = _query(db, source, WARNING_TABLE, "keyword")
        assert no_warning.results == []
        assert no_warning.related_tables == []
        for mode in ("keyword", "semantic", "hybrid"):
            result = _query(db, source, READY_TABLE, mode, provider=provider)
            assert (result.source_name, result.catalog_revision_id, result.schema_fingerprint) == (
                source, ready.id, ready.schema_fingerprint,
            )
            assert result.results
            assert {
                hit.document_key for hit in result.results
            } == {
                f"TABLE:DEMIS_OWNER.{READY_TABLE}",
                f"COLUMN:DEMIS_OWNER.{READY_TABLE}.ID",
            } or (
                mode == "keyword" and {
                    hit.document_key for hit in result.results
                } == {f"TABLE:DEMIS_OWNER.{READY_TABLE}"}
            )
            assert all(
                (
                    hit.identity.source_name, hit.identity.catalog_revision_id,
                    hit.identity.schema_fingerprint,
                ) == (source, ready.id, ready.schema_fingerprint)
                for hit in result.results
            )
            assert all("TB_VISIT" not in hit.document_key for hit in result.results)
            assert result.related_tables == []
            if mode != "keyword":
                assert result.model_key == provider.model_key
