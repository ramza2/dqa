"""P30-C: HTTP Data Discovery revision/source/index lifecycle on disposable PG.

No real DEMIS, Oracle, ModelOps, LLM, clinical data, or production DB calls.
This tests synchronous ASGI server contracts, NOT browser stale-request UI races.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.db.session import get_engine, get_session_factory
from app.api.routes import data_discovery as api_module
from app.core.config import get_settings
from app.main import create_app
from app.models.data_discovery import DataDiscoveryDocument
from app.services.catalog_active import activate_catalog_revision
from tests.fakes.embedding_provider import StubEmbeddingProvider
from tests.test_data_discovery_search import _make_revision

pytestmark = pytest.mark.integration
ROOT = "/api/v1/data-discovery"
ADMIN = {"X-DQA-Dev-Actor": "p30c-admin", "X-DQA-Dev-Roles": "administrator"}
VIEWER = {"X-DQA-Dev-Actor": "p30c-viewer", "X-DQA-Dev-Roles": "viewer"}
SOURCE_A = "p30c_synthetic_alpha"
SOURCE_B = "p30c_synthetic_beta"


@pytest.fixture()
def api(
    p30c_factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, sessionmaker[Session], list[StubEmbeddingProvider]]]:
    providers: list[StubEmbeddingProvider] = []

    def _stub(_settings: object) -> StubEmbeddingProvider:
        provider = StubEmbeddingProvider()
        providers.append(provider)
        return provider

    monkeypatch.setattr(api_module, "create_embedding_provider", _stub)
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    with TestClient(create_app(check_migrations_on_startup=True), headers=ADMIN) as client:
        yield client, p30c_factory, providers
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def _seed(
    factory: sessionmaker[Session], *, source: str, fingerprint: str,
    tables: tuple[str, ...], activate: bool = True,
) -> int:
    archive_sha = hashlib.sha256(f"{source}:{fingerprint}".encode()).hexdigest()
    with factory.begin() as db:
        revision = _make_revision(
            db, source_name=source, fingerprint=fingerprint,
            archive_sha256=archive_sha,
        )
        revision.tables_json = {
            "tables": [
                {
                    "table_key": f"DEMIS_OWNER.{name}",
                    "schema_name": "DEMIS_OWNER",
                    "table_name": name,
                    "table_comment": "synthetic metadata only",
                }
                for name in tables
            ]
        }
        revision.table_count = len(tables)
        revision.columns_json = {"columns": []}
        revision.column_count = 0
        revision.relations_json = {"relations": []}
        revision.relation_count = 0
        revision.indexes_json = {"indexes": []}
        if activate:
            assert activate_catalog_revision(db, revision.id).changed
        return revision.id


def _search(
    client: TestClient, source: str, query: str, mode: str
) -> Any:
    return client.post(
        f"{ROOT}/search",
        json={
            "source_name": source, "query": query, "mode": mode, "top_k": 10,
            "expand_terms": False, "expand_relations": False,
        },
    )


def _assert_bound(body: dict[str, Any], source: str, revision: int, fp: str) -> None:
    assert (body["source_name"], body["catalog_revision_id"],
            body["schema_fingerprint"]) == (source, revision, fp)
    for rank, hit in enumerate(body["results"], start=1):
        assert hit["rank"] == rank
        ident = hit["identity"]
        assert (
            ident["source_name"], ident["catalog_revision_id"],
            ident["schema_fingerprint"],
        ) == (source, revision, fp)
        assert hit["document_key"].startswith("TABLE:DEMIS_OWNER.")


def _rebuild(client: TestClient, source: str, revision: int) -> dict[str, Any]:
    res = client.post(f"{ROOT}/{source}/documents/rebuild")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source_name"] == source
    assert body["catalog_revision_id"] == revision
    return body


def _sync(client: TestClient, source: str, revision: int) -> dict[str, Any]:
    res = client.post(f"{ROOT}/{source}/embeddings/sync")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["source_name"] == source
    assert body["catalog_revision_id"] == revision
    assert body["coverage"]["missing_count"] == 0
    assert body["coverage"]["stale_count"] == 0
    return body


def _status(client: TestClient, source: str, revision: int) -> dict[str, Any]:
    res = client.get(f"{ROOT}/{source}/index-status")
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["source_name"], body["catalog_revision_id"]) == (source, revision)
    return body


def test_two_sources_same_key_keyword_semantic_hybrid_never_cross(
    api: tuple[TestClient, sessionmaker[Session], list[StubEmbeddingProvider]],
) -> None:
    client, factory, providers = api
    a = _seed(factory, source=SOURCE_A, fingerprint="p30c-a1", tables=("TB_SHARED", "TB_A_ONLY"))
    b = _seed(factory, source=SOURCE_B, fingerprint="p30c-b1", tables=("TB_SHARED", "TB_B_ONLY"))
    for source, revision in ((SOURCE_A, a), (SOURCE_B, b)):
        assert _rebuild(client, source, revision)["document_count"] == 2
        assert _sync(client, source, revision)["document_count"] == 2
        assert _status(client, source, revision)["embedding_state"] == "READY"

    for mode in ("keyword", "semantic", "hybrid"):
        for source, revision, fp, forbidden in (
            (SOURCE_A, a, "p30c-a1", "TB_B_ONLY"),
            (SOURCE_B, b, "p30c-b1", "TB_A_ONLY"),
        ):
            res = _search(client, source, "TB_SHARED", mode)
            assert res.status_code == 200, res.text
            body = res.json()
            _assert_bound(body, source, revision, fp)
            assert body["results"]
            assert all(forbidden not in hit["document_key"] for hit in body["results"])
            assert any("TB_SHARED" in hit["document_key"] for hit in body["results"])
    assert providers
    assert all(provider._closed for provider in providers)
    # Stubs are deterministic hash vectors, NOT clinical relevance measurements.


def test_revision_switch_requires_new_documents_and_embeddings_before_search(
    api: tuple[TestClient, sessionmaker[Session], list[StubEmbeddingProvider]],
) -> None:
    client, factory, _ = api
    a1 = _seed(factory, source=SOURCE_A, fingerprint="p30c-cut-a1", tables=("TB_OLD_ONLY",))
    b1 = _seed(factory, source=SOURCE_B, fingerprint="p30c-cut-b1", tables=("TB_B_ONLY",))
    for source, revision in ((SOURCE_A, a1), (SOURCE_B, b1)):
        _rebuild(client, source, revision)
        _sync(client, source, revision)

    a2 = _seed(factory, source=SOURCE_A, fingerprint="p30c-cut-a2", tables=("TB_NEW_ONLY",))
    # Old revision and its embeddings remain stored but cannot satisfy new active index.
    initial = _status(client, SOURCE_A, a2)
    assert initial["document_count"] == 0
    assert initial["document_state"] == "NOT_READY"
    for mode in ("keyword", "semantic", "hybrid"):
        result = _search(client, SOURCE_A, "TB_OLD_ONLY", mode)
        assert result.status_code == 409, result.text
        assert result.json()["detail"]["code"] == "DISCOVERY_INDEX_NOT_READY"

    assert _rebuild(client, SOURCE_A, a2)["document_count"] == 1
    stage = _status(client, SOURCE_A, a2)
    assert stage["document_state"] == "READY"
    assert stage["embedding_state"] == "NOT_READY"
    assert stage["coverage"]["missing_count"] == 1
    old = _search(client, SOURCE_A, "TB_OLD_ONLY", "keyword")
    assert old.status_code == 200
    _assert_bound(old.json(), SOURCE_A, a2, "p30c-cut-a2")
    assert old.json()["results"] == []
    for mode in ("semantic", "hybrid"):
        result = _search(client, SOURCE_A, "TB_NEW_ONLY", mode)
        assert result.status_code == 409
        assert result.json()["detail"]["code"] == "EMBEDDING_NOT_READY"

    _sync(client, SOURCE_A, a2)
    assert _status(client, SOURCE_A, a2)["embedding_state"] == "READY"
    for mode in ("keyword", "semantic", "hybrid"):
        result = _search(client, SOURCE_A, "TB_NEW_ONLY", mode)
        assert result.status_code == 200, result.text
        body = result.json()
        _assert_bound(body, SOURCE_A, a2, "p30c-cut-a2")
        assert {hit["document_key"] for hit in body["results"]} == {
            "TABLE:DEMIS_OWNER.TB_NEW_ONLY",
        }

    assert _status(client, SOURCE_B, b1)["embedding_state"] == "READY"
    unchanged = _search(client, SOURCE_B, "TB_B_ONLY", "hybrid")
    assert unchanged.status_code == 200
    _assert_bound(unchanged.json(), SOURCE_B, b1, "p30c-cut-b1")
    with factory() as db:
        old_docs = list(db.scalars(select(DataDiscoveryDocument).where(
            DataDiscoveryDocument.catalog_import_revision_id == a1,
        )).all())
    assert len(old_docs) == 1  # immutable history was not erased by Source A switch


def test_rebuild_and_embedding_sync_idempotent_for_current_revision(
    api: tuple[TestClient, sessionmaker[Session], list[StubEmbeddingProvider]],
) -> None:
    client, factory, providers = api
    rev = _seed(factory, source=SOURCE_A, fingerprint="p30c-idempotent", tables=("TB_STABLE",))
    first = _rebuild(client, SOURCE_A, rev)
    assert first["upserted_count"] == 1
    second = _rebuild(client, SOURCE_A, rev)
    assert second["upserted_count"] == 0
    first_sync = _sync(client, SOURCE_A, rev)
    assert first_sync["embedded_count"] == 1
    second_sync = _sync(client, SOURCE_A, rev)
    assert second_sync["embedded_count"] == 0
    assert second_sync["skipped_count"] == 1
    assert _status(client, SOURCE_A, rev)["embedding_state"] == "READY"
    # Repeated status calls require only model metadata, never embedding generation.
    before = sum(len(p.query_texts) + len(p.document_texts) for p in providers)
    _status(client, SOURCE_A, rev)
    after = sum(len(p.query_texts) + len(p.document_texts) for p in providers)
    assert before == after


def test_discovery_manage_rbac_and_unknown_source_fail_closed(
    api: tuple[TestClient, sessionmaker[Session], list[StubEmbeddingProvider]],
) -> None:
    client, factory, providers = api
    rev = _seed(factory, source=SOURCE_A, fingerprint="p30c-rbac", tables=("TB_ACCESS",))
    for method, url, data in (
        ("GET", f"{ROOT}/{SOURCE_A}/index-status", None),
        ("POST", f"{ROOT}/search", {
            "source_name": SOURCE_A, "query": "TB_ACCESS", "mode": "keyword"
        }),
        ("POST", f"{ROOT}/{SOURCE_A}/documents/rebuild", None),
        ("POST", f"{ROOT}/{SOURCE_A}/embeddings/sync", None),
    ):
        response = client.request(method, url, headers=VIEWER, json=data)
        assert response.status_code == 403, response.text

    assert _status(client, SOURCE_A, rev)["document_state"] == "NOT_READY"
    unknown = client.get(f"{ROOT}/p30c_missing_source/index-status")
    assert unknown.status_code == 404
    assert unknown.json()["detail"]["code"] == "ACTIVE_REVISION_NOT_FOUND"
    assert providers  # status fetched stub metadata, no external model calls
    assert all(not p.query_texts and not p.document_texts for p in providers)
