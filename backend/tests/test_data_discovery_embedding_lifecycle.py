"""Phase 27-B: embedding sync lifecycle and coverage status."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.adapters.data_discovery.errors import DataDiscoveryErrorCode
from app.core.config import get_settings
from app.models.catalog_import import CatalogImportRevision
from app.models.data_discovery_embedding import DataDiscoveryEmbedding
from app.repositories.data_discovery import DataDiscoveryRepository
from app.repositories.data_discovery_embedding import DataDiscoveryEmbeddingRepository
from app.services.data_discovery_document import rebuild_for_revision
from app.services.data_discovery_embedding import (
    embedding_status_for_revision,
    sync_embeddings_for_revision,
)
from tests.fakes.embedding_provider import StubEmbeddingProvider

pytestmark = pytest.mark.integration


def _payload() -> dict[str, Any]:
    return {
        "fingerprint": "fp-emb-a",
        "tables": [
            {
                "table_key": "DEMIS_OWNER.TB_LAB",
                "schema_name": "DEMIS_OWNER",
                "table_name": "TB_LAB",
                "table_comment": "laboratory results",
            },
            {
                "table_key": "DEMIS_OWNER.TB_ADM",
                "schema_name": "DEMIS_OWNER",
                "table_name": "TB_ADM",
                "table_comment": "admission",
            },
        ],
        "columns": [
            {
                "table_key": "DEMIS_OWNER.TB_LAB",
                "column_name": "GLUCOSE",
                "data_type": "NUMBER",
                "column_comment": "blood glucose",
            },
            {
                "table_key": "DEMIS_OWNER.TB_ADM",
                "column_name": "ADM_ID",
                "data_type": "NUMBER",
                "primary_key": True,
            },
        ],
        "relations": [],
        "indexes": [],
        "categories": [],
        "assignments": [],
    }


def _make_revision(
    session: Session,
    *,
    fingerprint: str = "fp-emb-a",
    archive_sha256: str = "e" * 64,
    payload: dict[str, Any] | None = None,
) -> CatalogImportRevision:
    data = payload or _payload()
    data = {**data, "fingerprint": fingerprint}
    revision = CatalogImportRevision(
        source_name="oracle_demis_mock",
        db_type="oracle",
        database_name="FREEPDB1",
        default_schema="DEMIS_OWNER",
        package_format="demis-catalog-package",
        package_version="2.0",
        package_readiness="READY",
        schema_fingerprint=fingerprint,
        archive_sha256=archive_sha256,
        manifest_sha256="f" * 64,
        generated_at=datetime(2026, 10, 8, tzinfo=UTC),
        validation_status="VALID",
        table_count=len(data["tables"]),
        column_count=len(data["columns"]),
        relation_count=0,
        index_count=0,
        category_count=0,
        category_assignment_count=0,
        managed_file_count=1,
        manifest_json={},
        database_json={},
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


def test_embedding_sync_skip_and_reembed(db_session: Session) -> None:
    rev = _make_revision(db_session)
    rebuild_for_revision(db_session, rev.id)
    db_session.flush()
    provider = StubEmbeddingProvider()

    first = sync_embeddings_for_revision(db_session, rev.id, provider, batch_size=2)
    db_session.flush()
    assert first.embedded_count == first.document_count == 4
    assert first.skipped_count == 0

    second = sync_embeddings_for_revision(db_session, rev.id, provider, batch_size=2)
    db_session.flush()
    assert second.embedded_count == 0
    assert second.skipped_count == 4

    docs = DataDiscoveryRepository(db_session).list_for_revision(rev.id)
    target = next(d for d in docs if d.table_name == "TB_LAB" and d.object_type == "TABLE")
    target.searchable_text = target.searchable_text + "\nnote: changed"
    target.document_fingerprint = "changed-fingerprint"
    db_session.flush()

    third = sync_embeddings_for_revision(db_session, rev.id, provider, batch_size=2)
    db_session.flush()
    assert third.embedded_count == 1
    assert third.skipped_count == 3

    status = embedding_status_for_revision(db_session, rev.id, provider.model_key)
    assert status.document_count == 4
    assert status.current_count == 4
    assert status.missing_count == 0
    assert status.stale_count == 0
    assert status.is_ready


def test_embedding_revision_and_model_key_isolation(db_session: Session) -> None:
    rev_a = _make_revision(db_session, fingerprint="fp-emb-a", archive_sha256="a" * 64)
    rev_b = _make_revision(
        db_session,
        fingerprint="fp-emb-b",
        archive_sha256="b" * 64,
        payload={**_payload(), "fingerprint": "fp-emb-b"},
    )
    rebuild_for_revision(db_session, rev_a.id)
    rebuild_for_revision(db_session, rev_b.id)
    db_session.flush()

    provider_a = StubEmbeddingProvider(model_name="model-a")
    provider_b = StubEmbeddingProvider(model_name="model-b")
    sync_embeddings_for_revision(db_session, rev_a.id, provider_a)
    sync_embeddings_for_revision(db_session, rev_b.id, provider_a)
    sync_embeddings_for_revision(db_session, rev_a.id, provider_b)
    db_session.flush()

    repo = DataDiscoveryEmbeddingRepository(db_session)
    assert repo.count_for_revision_and_model(rev_a.id, provider_a.model_key) == 4
    assert repo.count_for_revision_and_model(rev_b.id, provider_a.model_key) == 4
    assert repo.count_for_revision_and_model(rev_a.id, provider_b.model_key) == 4
    assert repo.count_for_revision_and_model(rev_b.id, provider_b.model_key) == 0


def test_dimension_mismatch_rejected(db_session: Session) -> None:
    rev = _make_revision(db_session)
    rebuild_for_revision(db_session, rev.id)
    db_session.flush()
    bad = StubEmbeddingProvider(dimension=768)
    with pytest.raises(Exception) as exc:
        sync_embeddings_for_revision(db_session, rev.id, bad)
    assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_DIMENSION_MISMATCH


def test_migration_embeddings_table_and_extension(
    test_settings_env: dict[str, str],
) -> None:
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect

    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    assert list(script.get_heads()) == ["20261008_dd02"]
    assert script.get_revision("20261008_dd02").down_revision == "20261008_dd01"

    engine = get_engine()
    command.upgrade(cfg, "head")
    insp = inspect(engine)
    assert insp.has_table("data_discovery_embeddings")
    with engine.begin() as conn:
        ext = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        ).scalar()
        assert ext == "vector"
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    assert version == "20261008_dd02"

    uqs = {
        uq["name"] for uq in insp.get_unique_constraints("data_discovery_embeddings")
    }
    assert "uq_data_discovery_embeddings_document_model_key" in uqs
    cols = {c["name"] for c in insp.get_columns("data_discovery_embeddings")}
    assert "embedding" in cols
    assert DataDiscoveryEmbedding.__tablename__ == "data_discovery_embeddings"

    command.downgrade(cfg, "20261008_dd01")
    with engine.begin() as conn:
        ext_after = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname='vector'")
        ).scalar()
        version_after = conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
    assert ext_after == "vector"
    assert version_after == "20261008_dd01"
    assert not inspect(engine).has_table("data_discovery_embeddings")
    command.upgrade(cfg, "head")
