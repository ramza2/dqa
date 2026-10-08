"""Phase 27-B: OpenAI-compatible embedding provider tests (no external network)."""

from __future__ import annotations

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.data_discovery.errors import DataDiscoveryErrorCode
from app.adapters.embedding.factory import create_embedding_provider
from app.adapters.embedding.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
    normalize_embeddings_url,
)
from app.core.config import Settings
from app.domain.data_discovery import build_embedding_model_key
from app.models.data_discovery_embedding import EMBEDDING_VECTOR_DIMENSION


def _vector(dim: int = EMBEDDING_VECTOR_DIMENSION, fill: float = 0.1) -> list[float]:
    return [fill] * dim


def _transport(handler):
    return httpx.MockTransport(handler)


def test_url_normalization() -> None:
    assert (
        normalize_embeddings_url("https://example.test")
        == "https://example.test/v1/embeddings"
    )
    assert (
        normalize_embeddings_url("https://example.test/v1")
        == "https://example.test/v1/embeddings"
    )
    assert (
        normalize_embeddings_url("https://example.test/v1/")
        == "https://example.test/v1/embeddings"
    )


def test_authorization_header_and_no_key_when_empty() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": _vector()}]},
        )

    with OpenAICompatibleEmbeddingProvider(
        base_url="https://example.test",
        model="bge-m3",
        api_key=SecretStr("secret-token"),
        transport=_transport(handler),
    ) as provider:
        provider.embed_queries(["q"])
    assert seen["authorization"] == "Bearer secret-token"

    seen.clear()

    def handler_no_key(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": _vector()}]},
        )

    with OpenAICompatibleEmbeddingProvider(
        base_url="https://example.test",
        model="bge-m3",
        api_key=SecretStr(""),
        transport=_transport(handler_no_key),
    ) as provider:
        provider.embed_queries(["q"])
    assert seen["authorization"] is None


def test_prefix_application_and_index_ordering() -> None:
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        import json

        body = json.loads(payload.decode("utf-8"))
        captured.extend(body["input"])
        inputs = body["input"]
        # Return reversed indexes to force reorder.
        data = [
            {"index": index, "embedding": _vector(fill=0.1 * (index + 1))}
            for index in range(len(inputs))
        ]
        data.reverse()
        return httpx.Response(200, json={"data": data})

    with OpenAICompatibleEmbeddingProvider(
        base_url="https://example.test",
        model="bge-m3",
        query_prefix="query: ",
        document_prefix="passage: ",
        normalized=False,
        transport=_transport(handler),
    ) as provider:
        docs = provider.embed_documents(["alpha", "beta"])
        queries = provider.embed_queries(["gamma"])
    assert captured == ["passage: alpha", "passage: beta", "query: gamma"]
    assert docs[0][0] == pytest.approx(0.1)
    assert docs[1][0] == pytest.approx(0.2)
    assert queries[0][0] == pytest.approx(0.1)


def test_dimension_mismatch_and_zero_vector_rejected() -> None:
    def bad_dim(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]},
        )

    with OpenAICompatibleEmbeddingProvider(
        base_url="https://example.test",
        model="bge-m3",
        transport=_transport(bad_dim),
    ) as provider:
        with pytest.raises(Exception) as exc:
            provider.embed_queries(["q"])
        assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_DIMENSION_MISMATCH

    def zero_vec(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": _vector(fill=0.0)}]},
        )

    with OpenAICompatibleEmbeddingProvider(
        base_url="https://example.test",
        model="bge-m3",
        normalized=True,
        transport=_transport(zero_vec),
    ) as provider:
        with pytest.raises(Exception) as exc:
            provider.embed_queries(["q"])
        assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_INVALID_RESPONSE
        assert "secret" not in str(exc.value).casefold()
        assert "patient" not in str(exc.value).casefold()


def test_http_timeout_and_errors_sanitized() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    with OpenAICompatibleEmbeddingProvider(
        base_url="https://example.test/private-path",
        model="bge-m3",
        api_key=SecretStr("super-secret-key"),
        transport=_transport(timeout),
    ) as provider:
        with pytest.raises(Exception) as exc:
            provider.embed_queries(["sensitive-query-text"])
        message = str(exc.value)
        assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_TIMEOUT
        assert "super-secret-key" not in message
        assert "sensitive-query-text" not in message
        assert "private-path" not in message


def test_close_idempotent_and_trust_env_false() -> None:
    provider = OpenAICompatibleEmbeddingProvider(
        base_url="https://example.test",
        model="bge-m3",
        transport=_transport(
            lambda _r: httpx.Response(
                200, json={"data": [{"index": 0, "embedding": _vector()}]}
            )
        ),
    )
    assert provider._client._trust_env is False  # noqa: SLF001
    provider.close()
    provider.close()


def test_model_key_ignores_endpoint_url() -> None:
    key_a = build_embedding_model_key(
        provider="openai_compatible",
        model_name="bge-m3",
        model_revision="1",
        dimension=1024,
        normalized=True,
        query_prefix="q:",
        document_prefix="d:",
    )
    with OpenAICompatibleEmbeddingProvider(
        base_url="https://host-a.example",
        model="bge-m3",
        model_revision="1",
        query_prefix="q:",
        document_prefix="d:",
        transport=_transport(
            lambda _r: httpx.Response(
                200, json={"data": [{"index": 0, "embedding": _vector()}]}
            )
        ),
    ) as provider_a:
        assert provider_a.model_key == key_a
    with OpenAICompatibleEmbeddingProvider(
        base_url="https://host-b.example/v1",
        model="bge-m3",
        model_revision="1",
        query_prefix="q:",
        document_prefix="d:",
        transport=_transport(
            lambda _r: httpx.Response(
                200, json={"data": [{"index": 0, "embedding": _vector()}]}
            )
        ),
    ) as provider_b:
        assert provider_b.model_key == key_a

    changed = build_embedding_model_key(
        provider="openai_compatible",
        model_name="bge-m3",
        model_revision="2",
        dimension=1024,
        normalized=True,
        query_prefix="q:",
        document_prefix="d:",
    )
    assert changed != key_a


def test_factory_requires_config_and_dimension() -> None:
    with pytest.raises(Exception) as exc:
        create_embedding_provider(
            Settings(embedding_base_url="", embedding_model="x")
        )
    assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_NOT_CONFIGURED

    with pytest.raises(Exception) as exc:
        create_embedding_provider(
            Settings(
                embedding_base_url="https://example.test",
                embedding_model="bge-m3",
                embedding_dimension=768,
            )
        )
    assert exc.value.code == DataDiscoveryErrorCode.EMBEDDING_DIMENSION_MISMATCH
