"""Typed errors for the embedding provider adapter boundary."""

from __future__ import annotations

from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode

# Re-export under embedding-local aliases for adapter callers.
EmbeddingProviderError = DataDiscoveryError
EmbeddingProviderErrorCode = DataDiscoveryErrorCode

__all__ = ["EmbeddingProviderError", "EmbeddingProviderErrorCode"]
