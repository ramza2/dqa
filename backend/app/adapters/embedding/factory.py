"""Factory for constructing the configured embedding provider."""

from __future__ import annotations

from app.adapters.embedding.base import EmbeddingProvider
from app.adapters.embedding.errors import EmbeddingProviderError, EmbeddingProviderErrorCode
from app.adapters.embedding.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.core.config import Settings
from app.models.data_discovery_embedding import EMBEDDING_VECTOR_DIMENSION


def create_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Build the OpenAI-compatible embedding provider from settings.

    Application startup must succeed without embedding settings. Completeness is
    checked only when a provider is constructed for use.
    """
    base_url = (settings.embedding_base_url or "").strip()
    model = (settings.embedding_model or "").strip()

    if not base_url:
        raise EmbeddingProviderError(
            EmbeddingProviderErrorCode.EMBEDDING_NOT_CONFIGURED,
            "embedding base URL is not configured",
        )
    if not model:
        raise EmbeddingProviderError(
            EmbeddingProviderErrorCode.EMBEDDING_NOT_CONFIGURED,
            "embedding model is not configured",
        )
    if settings.embedding_dimension != EMBEDDING_VECTOR_DIMENSION:
        raise EmbeddingProviderError(
            EmbeddingProviderErrorCode.EMBEDDING_DIMENSION_MISMATCH,
            "embedding dimension is not supported by this implementation",
        )

    query_prefix = settings.embedding_query_prefix
    document_prefix = settings.embedding_document_prefix
    return OpenAICompatibleEmbeddingProvider(
        base_url=base_url,
        model=model,
        api_key=settings.embedding_api_key,
        model_revision=settings.embedding_model_revision,
        dimension=settings.embedding_dimension,
        normalized=settings.embedding_normalize,
        query_prefix=query_prefix.strip() if query_prefix else None,
        document_prefix=document_prefix.strip() if document_prefix else None,
        timeout_seconds=settings.embedding_timeout_seconds,
        connect_timeout_seconds=settings.embedding_connect_timeout_seconds,
    )
