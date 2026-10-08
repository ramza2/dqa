"""OpenAI-compatible Embeddings provider (httpx)."""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import SecretStr

from app.adapters.embedding.errors import EmbeddingProviderError, EmbeddingProviderErrorCode
from app.domain.data_discovery import build_embedding_model_key
from app.models.data_discovery_embedding import EMBEDDING_VECTOR_DIMENSION

_PROVIDER_NAME = "openai_compatible"


def normalize_embeddings_url(base_url: str) -> str:
    """Build ``.../v1/embeddings`` without duplicating ``/v1``."""
    trimmed = base_url.strip().rstrip("/")
    if not trimmed:
        raise EmbeddingProviderError(
            EmbeddingProviderErrorCode.EMBEDDING_NOT_CONFIGURED,
            "embedding base URL is not configured",
        )
    if trimmed.endswith("/v1"):
        return f"{trimmed}/embeddings"
    return f"{trimmed}/v1/embeddings"


class OpenAICompatibleEmbeddingProvider:
    """OpenAI-compatible Embeddings client.

    Does not log texts, response bodies, API keys, or endpoints. Does not retry.
    Uses ``trust_env=False`` for owned httpx clients.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: SecretStr | str | None = None,
        model_revision: str | None = None,
        dimension: int = EMBEDDING_VECTOR_DIMENSION,
        normalized: bool = True,
        query_prefix: str | None = None,
        document_prefix: str | None = None,
        timeout_seconds: float = 60.0,
        connect_timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        model_stripped = model.strip() if isinstance(model, str) else ""
        if not model_stripped:
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_NOT_CONFIGURED,
                "embedding model is not configured",
            )
        if dimension != EMBEDDING_VECTOR_DIMENSION:
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_DIMENSION_MISMATCH,
                "embedding dimension is not supported by this implementation",
            )
        self._endpoint = normalize_embeddings_url(base_url)
        self._model = model_stripped
        self._model_revision = (
            model_revision.strip()
            if isinstance(model_revision, str) and model_revision.strip()
            else None
        )
        self._dimension = dimension
        self._normalized = bool(normalized)
        self._query_prefix = query_prefix if query_prefix else None
        self._document_prefix = document_prefix if document_prefix else None
        self._api_key = _optional_secret(api_key)
        self._model_key = build_embedding_model_key(
            provider=_PROVIDER_NAME,
            model_name=self._model,
            model_revision=self._model_revision,
            dimension=self._dimension,
            normalized=self._normalized,
            query_prefix=self._query_prefix,
            document_prefix=self._document_prefix,
        )
        self._owns_client = client is None
        self._closed = False
        timeout = httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds)
        if client is not None:
            self._client = client
        else:
            self._client = httpx.Client(
                timeout=timeout,
                transport=transport,
                trust_env=False,
            )

    @property
    def provider_name(self) -> str:
        return _PROVIDER_NAME

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def model_revision(self) -> str | None:
        return self._model_revision

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def normalized(self) -> bool:
        return self._normalized

    @property
    def model_key(self) -> str:
        return self._model_key

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenAICompatibleEmbeddingProvider:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, prefix=self._document_prefix)

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed(texts, prefix=self._query_prefix)

    def _embed(self, texts: Sequence[str], *, prefix: str | None) -> list[list[float]]:
        if not texts:
            return []
        payload_input = [f"{prefix}{text}" if prefix else text for text in texts]
        response = self._post({"model": self._model, "input": payload_input})
        vectors = self._parse_vectors(response, expected=len(texts))
        if self._normalized:
            vectors = [_l2_normalize(vector) for vector in vectors]
        return vectors

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        try:
            response = self._client.post(
                self._endpoint,
                headers=self._headers(),
                json=payload,
            )
        except httpx.TimeoutException:
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_TIMEOUT,
                "embedding provider request timed out",
            ) from None
        except httpx.NetworkError:
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_CONNECTION_FAILED,
                "embedding provider connection failed",
            ) from None
        except httpx.HTTPError:
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_CONNECTION_FAILED,
                "embedding provider transport error",
            ) from None

        if response.status_code < 200 or response.status_code >= 300:
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_HTTP_ERROR,
                f"embedding provider returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        return response

    def _parse_vectors(self, response: httpx.Response, *, expected: int) -> list[list[float]]:
        try:
            body: Any = response.json()
        except (json.JSONDecodeError, ValueError):
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                "embedding provider returned non-JSON response body",
            ) from None
        if not isinstance(body, dict):
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                "embedding provider response must be a JSON object",
            )
        data = body.get("data")
        if not isinstance(data, list) or not data:
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                "embedding provider response is missing data",
            )
        if len(data) != expected:
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                "embedding provider returned unexpected vector count",
            )

        indexed: list[tuple[int, list[float]]] = []
        for entry in data:
            if not isinstance(entry, dict):
                raise EmbeddingProviderError(
                    EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                    "embedding provider data entry is invalid",
                )
            index = entry.get("index")
            embedding = entry.get("embedding")
            if not isinstance(index, int) or isinstance(index, bool):
                raise EmbeddingProviderError(
                    EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                    "embedding provider data index is invalid",
                )
            if not isinstance(embedding, list) or not embedding:
                raise EmbeddingProviderError(
                    EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                    "embedding provider vector is invalid",
                )
            if len(embedding) != self._dimension:
                raise EmbeddingProviderError(
                    EmbeddingProviderErrorCode.EMBEDDING_DIMENSION_MISMATCH,
                    "embedding provider vector dimension mismatch",
                )
            values: list[float] = []
            for item in embedding:
                if isinstance(item, bool) or not isinstance(item, (int, float)):
                    raise EmbeddingProviderError(
                        EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                        "embedding provider vector contains non-numeric values",
                    )
                values.append(float(item))
            if self._normalized and all(value == 0.0 for value in values):
                raise EmbeddingProviderError(
                    EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                    "embedding provider returned a zero vector",
                )
            indexed.append((index, values))

        indexed.sort(key=lambda item: item[0])
        if [item[0] for item in indexed] != list(range(expected)):
            raise EmbeddingProviderError(
                EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
                "embedding provider data indexes are not contiguous",
            )
        return [item[1] for item in indexed]


def _optional_secret(api_key: SecretStr | str | None) -> str | None:
    if api_key is None:
        return None
    if isinstance(api_key, SecretStr):
        value = api_key.get_secret_value()
    else:
        value = api_key
    stripped = value.strip()
    return stripped or None


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise EmbeddingProviderError(
            EmbeddingProviderErrorCode.EMBEDDING_INVALID_RESPONSE,
            "embedding provider returned a zero vector",
        )
    return [value / norm for value in vector]
