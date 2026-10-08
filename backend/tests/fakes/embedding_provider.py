"""In-process stub embedding provider for Data Discovery tests (no network)."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from app.domain.data_discovery import build_embedding_model_key
from app.models.data_discovery_embedding import EMBEDDING_VECTOR_DIMENSION


class StubEmbeddingProvider:
    def __init__(
        self,
        *,
        model_name: str = "stub-bge-m3",
        model_revision: str | None = "test",
        dimension: int = EMBEDDING_VECTOR_DIMENSION,
        normalized: bool = True,
        query_prefix: str | None = None,
        document_prefix: str | None = None,
        provider_name: str = "openai_compatible",
    ) -> None:
        self._provider_name = provider_name
        self._model_name = model_name
        self._model_revision = model_revision
        self._dimension = dimension
        self._normalized = normalized
        self._query_prefix = query_prefix
        self._document_prefix = document_prefix
        self._closed = False
        self._model_key = build_embedding_model_key(
            provider=provider_name,
            model_name=model_name,
            model_revision=model_revision,
            dimension=dimension,
            normalized=normalized,
            query_prefix=query_prefix,
            document_prefix=document_prefix,
        )

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name

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

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        prefix = self._document_prefix or ""
        return [self._embed(prefix + text) for text in texts]

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        prefix = self._query_prefix or ""
        return [self._embed(prefix + text) for text in texts]

    def close(self) -> None:
        self._closed = True

    def _embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values: list[float] = []
        # Deterministic pseudo-embedding in R^dimension from hash stream.
        seed = digest
        while len(values) < self._dimension:
            seed = hashlib.sha256(seed).digest()
            for byte in seed:
                values.append(((byte / 255.0) * 2.0) - 1.0)
                if len(values) >= self._dimension:
                    break
        if self._normalized:
            norm = math.sqrt(sum(v * v for v in values)) or 1.0
            values = [v / norm for v in values]
        return values
