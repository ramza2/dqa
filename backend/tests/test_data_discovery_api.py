"""Phase 27-C: Data Discovery HTTP API tests (search, index status, rebuild, sync)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryErrorCode
from app.adapters.data_discovery.errors import DataDiscoveryErrorCode
from app.adapters.embedding.errors import EmbeddingProviderError, EmbeddingProviderErrorCode
from app.auth.errors import AuthErrorCode
from app.core.config import get_settings
from app.models.catalog_import import CatalogImportRevision
from app.services.catalog_active import activate_catalog_revision
from app.services.data_discovery_document import rebuild_for_revision
from app.services.data_discovery_embedding import sync_embeddings_for_revision
from tests.fakes.embedding_provider import StubEmbeddingProvider

pytestmark = pytest.mark.integration

SOURCE_NAME = "oracle_demis_mock"


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": actor,
        "X-DQA-Dev-Roles": roles,
    }


def _catalog_docs() -> dict[str, Any]:
    return {
        "tables": [
            {
                "table_key": "DEMIS_OWNER.TB_LAB_RESULT",
                "schema_name": "DEMIS_OWNER",
                "table_name": "TB_LAB_RESULT",
                "table_comment": "laboratory blood glucose panels",
            },
            {
                "table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "schema_name": "DEMIS_OWNER",
                "table_name": "TB_ADM_HIST",
                "table_comment": "patient admission history",
            },
        ],
        "columns": [
            {
                "table_key": "DEMIS_OWNER.TB_LAB_RESULT",
                "column_name": "GLUCOSE",
                "data_type": "NUMBER",
                "column_comment": "blood glucose value",
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
        ],
        "relations": [
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
        ],
        "indexes": [],
        "categories": [],
        "assignments": [],
    }


def _make_revision(
    session: Session,
    *,
    fingerprint: str = "fp-api-discovery-a",
    archive_sha256: str = "a" * 64,
) -> CatalogImportRevision:
    docs = _catalog_docs()
    revision = CatalogImportRevision(
        source_name=SOURCE_NAME,
        db_type="oracle",
        database_name="FREEPDB1",
        default_schema="DEMIS_OWNER",
        package_format="demis-catalog-package",
        package_version="2.0",
        package_readiness="READY",
        schema_fingerprint=fingerprint,
        archive_sha256=archive_sha256,
        manifest_sha256="b" * 64,
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


def _seed_active(
    session: Session,
    *,
    fingerprint: str = "fp-api-discovery-a",
    rebuild: bool = True,
) -> CatalogImportRevision:
    revision = _make_revision(session, fingerprint=fingerprint)
    activate_catalog_revision(session, revision.id)
    if rebuild:
        rebuild_for_revision(session, revision.id)
    session.commit()
    return revision


def _assert_no_sensitive_leak(payload: object) -> None:
    text = str(payload).lower()
    forbidden = (
        "api_key",
        "bearer ",
        "password",
        "secret",
        "http://",
        "https://",
        "searchable_text",
        "embedding_base_url",
        "postgresql://",
        "x-api-key",
    )
    for token in forbidden:
        assert token not in text


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_search_requires_catalog_read(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _seed_active(db_session)
    denied = unauth_db_client.post(
        "/api/v1/data-discovery/search",
        headers=_headers("no-perms", ""),
        json={"source_name": SOURCE_NAME, "query": "glucose", "mode": "keyword"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED
    _assert_no_sensitive_leak(denied.json())

    allowed = unauth_db_client.post(
        "/api/v1/data-discovery/search",
        headers=_headers("viewer", "viewer"),
        json={"source_name": SOURCE_NAME, "query": "glucose", "mode": "keyword"},
    )
    assert allowed.status_code == 200
    assert allowed.json()["mode"] == "keyword"


def test_manage_endpoints_require_catalog_manage(
    db_session: Session, unauth_db_client: TestClient
) -> None:
    _seed_active(db_session, rebuild=False)
    viewer = _headers("viewer", "viewer")
    rebuild = unauth_db_client.post(
        f"/api/v1/data-discovery/{SOURCE_NAME}/documents/rebuild",
        headers=viewer,
    )
    assert rebuild.status_code == 403
    assert rebuild.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED
    sync = unauth_db_client.post(
        f"/api/v1/data-discovery/{SOURCE_NAME}/embeddings/sync",
        headers=viewer,
    )
    assert sync.status_code == 403
    assert sync.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED


# ---------------------------------------------------------------------------
# Keyword search (no embedding)
# ---------------------------------------------------------------------------


def test_keyword_search_without_embedding_config(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active(db_session)
    get_settings.cache_clear()
    calls: list[object] = []

    def _factory(_settings: object) -> object:
        calls.append(_settings)
        raise AssertionError("factory must not be called for keyword mode")

    monkeypatch.setattr(
        "app.api.routes.data_discovery.create_embedding_provider",
        _factory,
    )
    response = db_client.post(
        "/api/v1/data-discovery/search",
        json={
            "source_name": SOURCE_NAME,
            "query": "glucose",
            "mode": "keyword",
            "expand_terms": False,
            "expand_relations": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "keyword"
    assert body["model_key"] is None
    assert body["results"]
    assert calls == []
    _assert_no_sensitive_leak(body)


# ---------------------------------------------------------------------------
# Semantic / hybrid
# ---------------------------------------------------------------------------


def test_semantic_without_provider_returns_503(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active(db_session)

    def _factory(_settings: object) -> object:
        raise EmbeddingProviderError(
            EmbeddingProviderErrorCode.EMBEDDING_NOT_CONFIGURED,
            "embedding base URL is not configured",
        )

    monkeypatch.setattr(
        "app.api.routes.data_discovery.create_embedding_provider",
        _factory,
    )
    response = db_client.post(
        "/api/v1/data-discovery/search",
        json={"source_name": SOURCE_NAME, "query": "glucose", "mode": "semantic"},
    )
    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == DataDiscoveryErrorCode.EMBEDDING_NOT_CONFIGURED
    _assert_no_sensitive_leak(response.json())


def test_hybrid_embedding_not_ready_409(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active(db_session)
    stub = StubEmbeddingProvider()

    monkeypatch.setattr(
        "app.api.routes.data_discovery.create_embedding_provider",
        lambda _s: stub,
    )
    response = db_client.post(
        "/api/v1/data-discovery/search",
        json={"source_name": SOURCE_NAME, "query": "glucose", "mode": "hybrid"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == DataDiscoveryErrorCode.EMBEDDING_NOT_READY
    assert stub._closed is True
    _assert_no_sensitive_leak(response.json())


def test_hybrid_ready_with_stub_provider_success(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _seed_active(db_session)
    stub = StubEmbeddingProvider()
    sync_embeddings_for_revision(db_session, revision.id, stub, batch_size=8)
    db_session.commit()
    stub.document_texts.clear()
    stub.query_texts.clear()
    stub._closed = False

    monkeypatch.setattr(
        "app.api.routes.data_discovery.create_embedding_provider",
        lambda _s: stub,
    )
    response = db_client.post(
        "/api/v1/data-discovery/search",
        json={
            "source_name": SOURCE_NAME,
            "query": "glucose",
            "mode": "hybrid",
            "top_k": 5,
            "expand_relations": True,
            "max_relation_hops": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "hybrid"
    assert body["model_key"] == stub.model_key
    assert body["results"]
    assert stub.query_texts
    assert stub._closed is True
    _assert_no_sensitive_leak(body)


# ---------------------------------------------------------------------------
# Index status
# ---------------------------------------------------------------------------


def test_index_status_document_not_ready(
    db_session: Session, db_client: TestClient
) -> None:
    _seed_active(db_session, rebuild=False)
    response = db_client.get(f"/api/v1/data-discovery/{SOURCE_NAME}/index-status")
    assert response.status_code == 200
    body = response.json()
    assert body["document_count"] == 0
    assert body["document_state"] == "NOT_READY"
    assert body["embedding_state"] == "NOT_CONFIGURED"
    assert body["coverage"] is None


def test_index_status_not_configured_is_200(
    db_session: Session, db_client: TestClient
) -> None:
    _seed_active(db_session)
    response = db_client.get(f"/api/v1/data-discovery/{SOURCE_NAME}/index-status")
    assert response.status_code == 200
    body = response.json()
    assert body["document_state"] == "READY"
    assert body["document_count"] > 0
    assert body["embedding_state"] == "NOT_CONFIGURED"
    _assert_no_sensitive_leak(body)


def test_index_status_configuration_error(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active(db_session)
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://example.invalid/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "test-model")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "512")
    get_settings.cache_clear()

    response = db_client.get(f"/api/v1/data-discovery/{SOURCE_NAME}/index-status")
    assert response.status_code == 200
    body = response.json()
    assert body["embedding_state"] == "CONFIGURATION_ERROR"
    assert body["embedding_error_code"] == DataDiscoveryErrorCode.EMBEDDING_DIMENSION_MISMATCH
    assert "example.invalid" not in str(body)
    _assert_no_sensitive_leak(body)
    get_settings.cache_clear()


def test_index_status_not_ready_and_ready_without_network(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _seed_active(db_session)
    stub = StubEmbeddingProvider()
    network_calls = 0

    def _factory(_settings: object) -> StubEmbeddingProvider:
        return stub

    original_embed_q = stub.embed_queries
    original_embed_d = stub.embed_documents

    def _q(texts: Any) -> list[list[float]]:
        nonlocal network_calls
        network_calls += 1
        return original_embed_q(texts)

    def _d(texts: Any) -> list[list[float]]:
        nonlocal network_calls
        network_calls += 1
        return original_embed_d(texts)

    stub.embed_queries = _q  # type: ignore[method-assign]
    stub.embed_documents = _d  # type: ignore[method-assign]
    monkeypatch.setattr(
        "app.api.routes.data_discovery.create_embedding_provider",
        _factory,
    )
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://example.invalid/v1")
    monkeypatch.setenv("EMBEDDING_MODEL", "stub-bge-m3")
    get_settings.cache_clear()

    missing = db_client.get(f"/api/v1/data-discovery/{SOURCE_NAME}/index-status")
    assert missing.status_code == 200
    assert missing.json()["embedding_state"] == "NOT_READY"
    assert missing.json()["coverage"]["missing_count"] > 0
    assert network_calls == 0
    assert stub._closed is True

    stub._closed = False
    sync_embeddings_for_revision(db_session, revision.id, StubEmbeddingProvider(), batch_size=8)
    db_session.commit()
    network_calls = 0

    ready = db_client.get(f"/api/v1/data-discovery/{SOURCE_NAME}/index-status")
    assert ready.status_code == 200
    body = ready.json()
    assert body["embedding_state"] == "READY"
    assert body["coverage"]["missing_count"] == 0
    assert body["coverage"]["stale_count"] == 0
    assert network_calls == 0
    assert stub._closed is True
    get_settings.cache_clear()


def test_index_status_active_missing_404(
    db_session: Session, db_client: TestClient
) -> None:
    response = db_client.get("/api/v1/data-discovery/unknown_source/index-status")
    assert response.status_code == 404
    assert (
        response.json()["detail"]["code"]
        == CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND
    )


# ---------------------------------------------------------------------------
# Rebuild / sync
# ---------------------------------------------------------------------------


def test_rebuild_exact_active_revision_no_embedding(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _seed_active(db_session, rebuild=False)
    factory_calls: list[object] = []

    def _factory(_settings: object) -> object:
        factory_calls.append(_settings)
        raise AssertionError("rebuild must not create embedding provider")

    monkeypatch.setattr(
        "app.api.routes.data_discovery.create_embedding_provider",
        _factory,
    )
    response = db_client.post(
        f"/api/v1/data-discovery/{SOURCE_NAME}/documents/rebuild",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["catalog_revision_id"] == revision.id
    assert body["source_name"] == SOURCE_NAME
    assert body["document_count"] > 0
    assert body["upserted_count"] > 0
    assert factory_calls == []


def test_sync_requires_documents(
    db_session: Session,
    db_client: TestClient,
) -> None:
    _seed_active(db_session, rebuild=False)
    no_docs = db_client.post(f"/api/v1/data-discovery/{SOURCE_NAME}/embeddings/sync")
    assert no_docs.status_code == 409
    assert no_docs.json()["detail"]["code"] == DataDiscoveryErrorCode.DISCOVERY_INDEX_NOT_READY
    _assert_no_sensitive_leak(no_docs.json())


def test_sync_success_with_stub(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revision = _seed_active(db_session)
    stub = StubEmbeddingProvider()
    monkeypatch.setattr(
        "app.api.routes.data_discovery.create_embedding_provider",
        lambda _s: stub,
    )
    response = db_client.post(f"/api/v1/data-discovery/{SOURCE_NAME}/embeddings/sync")
    assert response.status_code == 200
    body = response.json()
    assert body["catalog_revision_id"] == revision.id
    assert body["model_key"] == stub.model_key
    assert body["embedded_count"] > 0
    assert body["coverage"]["missing_count"] == 0
    assert stub.document_texts
    assert stub._closed is True
    _assert_no_sensitive_leak(body)


def test_sync_provider_missing_503(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_active(db_session)

    def _factory(_settings: object) -> object:
        raise EmbeddingProviderError(
            EmbeddingProviderErrorCode.EMBEDDING_NOT_CONFIGURED,
            "embedding base URL is not configured",
        )

    monkeypatch.setattr(
        "app.api.routes.data_discovery.create_embedding_provider",
        _factory,
    )
    response = db_client.post(f"/api/v1/data-discovery/{SOURCE_NAME}/embeddings/sync")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == DataDiscoveryErrorCode.EMBEDDING_NOT_CONFIGURED
    _assert_no_sensitive_leak(response.json())


# ---------------------------------------------------------------------------
# Catalog route regression smoke
# ---------------------------------------------------------------------------


def test_catalog_active_still_works(
    db_session: Session, db_client: TestClient
) -> None:
    _seed_active(db_session)
    response = db_client.get(f"/api/v1/catalog/active/{SOURCE_NAME}")
    assert response.status_code == 200
    assert response.json()["source_name"] == SOURCE_NAME
