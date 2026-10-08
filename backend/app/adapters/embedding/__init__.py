"""Embedding provider adapter package (OpenAI-compatible HTTP boundary)."""

from app.adapters.embedding.base import EmbeddingProvider
from app.adapters.embedding.errors import EmbeddingProviderError, EmbeddingProviderErrorCode
from app.adapters.embedding.factory import create_embedding_provider
from app.adapters.embedding.openai_compatible import (
    OpenAICompatibleEmbeddingProvider,
    normalize_embeddings_url,
)

__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingProviderErrorCode",
    "OpenAICompatibleEmbeddingProvider",
    "create_embedding_provider",
    "normalize_embeddings_url",
]
