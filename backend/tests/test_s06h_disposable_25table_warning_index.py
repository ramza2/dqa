"""S-06-H: synthetic 25-table WARNING Catalog on disposable loopback PG only.

Never use db_session/db_client (may TRUNCATE server DB). Existing guarded
S-06-A factory requires DQA_S06A_ISOLATED_PG=1 and fixed 127.0.0.1:55442.
No clinical data, live Oracle/DEMIS, DBA READY issuer or remote embedding.
"""
from __future__ import annotations

import pytest
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
from app.services.data_discovery_embedding import (
    embedding_status_for_revision, sync_embeddings_for_revision,
)
from app.services.data_discovery_search import search_schema
from tests.fakes.embedding_provider import StubEmbeddingProvider
from tests.test_s06a_disposable_pg_gold_search import factory
from tests.test_s06f_disposable_warning_search_isolation import _synthetic_ready_zip
from tests.test_s06g_25table_oracle_gold import _candidate, _inspect_25

pytestmark = pytest.mark.integration

SOURCE_ONLY = "s06h_25table_warning_only"
SOURCE_ACTIVE = "s06h_25table_ready_unchanged"
READY_TABLE = "TB_S06F_READY_ONLY"


def _warning_zip(source):
    archive, validated = _candidate(_inspect_25(), source=source)
    assert validated.package_readiness == "WARNING"
    assert not validated.activation_eligible
    assert validated.counts["tables"] == 25
    assert validated.counts["columns"] == 50
    return archive


def _query(db, source, query, *, mode="keyword", provider=None):
    return search_schema(
        db,
        DataDiscoverySearchRequest(
            source_name=source, query=query, mode=mode, top_k=10,
            expand_terms=False, expand_relations=True, max_relation_hops=1,
        ),
        embedding_provider=provider,
    )


def test_25table_warning_import_embedding_coverage_and_repeat_idempotence(factory):
    source = SOURCE_ONLY
    archive = _warning_zip(source)
    provider = StubEmbeddingProvider(model_name="s06h-local-stub")
    with factory() as db:
        imported, created = import_catalog_package_bytes(archive, db)
        assert created and imported.package_readiness == "WARNING"
        assert (imported.table_count, imported.column_count,
                imported.relation_count, imported.index_count) == (25, 50, 24, 24)
        revision_id = imported.id
        db.commit()

    with factory() as db:
        built = rebuild_for_revision(db, revision_id)
        assert (built.document_count, built.upserted_count, built.deleted_count) == (75, 75, 0)
        missing = embedding_status_for_revision(db, revision_id, provider.model_key)
        assert (missing.document_count, missing.current_count,
                missing.missing_count, missing.stale_count) == (75, 0, 75, 0)
        assert not missing.is_ready

        synced = sync_embeddings_for_revision(db, revision_id, provider, batch_size=16)
        assert (synced.document_count, synced.embedded_count,
                synced.skipped_count) == (75, 75, 0)
        assert len(provider.document_texts) == 75
        coverage = embedding_status_for_revision(db, revision_id, provider.model_key)
        assert (coverage.document_count, coverage.embedding_count,
                coverage.current_count, coverage.missing_count,
                coverage.stale_count) == (75, 75, 75, 0, 0)
        assert coverage.is_ready  # Embedding-only status, NOT Catalog READY

        with pytest.raises(CatalogActivationError) as denied:
            activate_catalog_revision(db, revision_id)
        assert denied.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
        db.commit()

    with factory() as db:
        again, created = import_catalog_package_bytes(archive, db)
        assert not created and again.id == revision_id
        rebuilt = rebuild_for_revision(db, revision_id)
        assert (rebuilt.document_count, rebuilt.deleted_count) == (75, 0)
        rerun = sync_embeddings_for_revision(db, revision_id, provider)
        assert (rerun.document_count, rerun.embedded_count, rerun.skipped_count) == (
            75, 0, 75,
        )
        assert len(provider.document_texts) == 75  # zero re-embedding
        rows = db.scalars(
            select(DataDiscoveryDocument).where(
                DataDiscoveryDocument.catalog_import_revision_id == revision_id
            )
        ).all()
        assert len(rows) == 75
        assert len({r.document_key for r in rows}) == 75
        assert all(
            (r.source_name, r.schema_fingerprint)
            == (source, again.schema_fingerprint)
            for r in rows
        )
        with pytest.raises(CatalogQueryError) as inaccessible:
            _query(db, source, "TB_GOLD_07")
        assert inaccessible.value.code == CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND
        assert db.scalars(select(CatalogActivationEvent).where(
            CatalogActivationEvent.source_name == source
        )).all() == []
        db.commit()


def test_ready_search_isolation_from_75_indexed_warning_documents(factory):
    source = SOURCE_ACTIVE
    provider = StubEmbeddingProvider(model_name="s06h-local-stub")
    with factory() as db:
        ready, created = import_catalog_package_bytes(_synthetic_ready_zip(source), db)
        assert created and ready.package_readiness == "READY"
        ready_id, ready_fingerprint = ready.id, ready.schema_fingerprint
        assert rebuild_for_revision(db, ready.id).document_count == 2
        assert sync_embeddings_for_revision(db, ready.id, provider).embedded_count == 2
        assert activate_catalog_revision(db, ready.id).changed
        db.commit()

    with factory() as db:
        before = get_active_catalog(db, source)
        assert before.revision_id == ready_id
        event_ids = db.scalars(
            select(CatalogActivationEvent.id)
            .where(CatalogActivationEvent.source_name == source)
            .order_by(CatalogActivationEvent.id)
        ).all()
        warning, created = import_catalog_package_bytes(_warning_zip(source), db)
        assert created and warning.package_readiness == "WARNING"
        assert warning.schema_fingerprint != ready_fingerprint
        warning_id = warning.id
        assert rebuild_for_revision(db, warning_id).document_count == 75
        assert sync_embeddings_for_revision(db, warning_id, provider).embedded_count == 75
        assert embedding_status_for_revision(
            db, warning_id, provider.model_key
        ).is_ready  # Indexed, never activated
        with pytest.raises(CatalogActivationError) as denied:
            activate_catalog_revision(db, warning_id)
        assert denied.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
        db.commit()

    with factory() as db:
        active = get_active_catalog(db, source)
        assert (active.revision_id, active.schema_fingerprint) == (
            ready_id, ready_fingerprint,
        )
        assert active.package_readiness == "READY"
        assert db.scalars(
            select(CatalogActivationEvent.id)
            .where(CatalogActivationEvent.source_name == source)
            .order_by(CatalogActivationEvent.id)
        ).all() == event_ids
        assert [row.name for row in list_tables(db, source)[1].items] == [READY_TABLE]

        hidden = _query(db, source, "TB_GOLD_07")
        assert hidden.results == [] and hidden.related_tables == []

        for mode in ("keyword", "semantic", "hybrid"):
            result = _query(db, source, READY_TABLE, mode=mode, provider=provider)
            assert (result.source_name, result.catalog_revision_id,
                    result.schema_fingerprint) == (source, ready_id, ready_fingerprint)
            assert result.results
            expected = {
                f"TABLE:DEMIS_OWNER.{READY_TABLE}",
                f"COLUMN:DEMIS_OWNER.{READY_TABLE}.ID",
            }
            assert {hit.document_key for hit in result.results} <= expected
            assert len({hit.document_key for hit in result.results}) == len(result.results)
            assert all(
                (hit.identity.source_name,
                 hit.identity.catalog_revision_id,
                 hit.identity.schema_fingerprint) == (
                    source, ready_id, ready_fingerprint,
                )
                for hit in result.results
            )
            assert result.related_tables == []
            if mode != "keyword":
                assert result.model_key == provider.model_key

        # All 75 WARNING derived documents remain immutable and revision-scoped.
        warning_rows = db.scalars(
            select(DataDiscoveryDocument).where(
                DataDiscoveryDocument.catalog_import_revision_id == warning_id
            )
        ).all()
        assert len(warning_rows) == 75
        assert all(r.source_name == source for r in warning_rows)
        assert all(r.schema_fingerprint != ready_fingerprint for r in warning_rows)
