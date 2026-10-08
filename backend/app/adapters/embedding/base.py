"""Vendor-independent embedding provider protocol."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class EmbeddingProvider(Protocol):
    """Application-facing embedding boundary."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def model_revision(self) -> str | None: ...

    @property
    def dimension(self) -> int: ...

    @property
    def normalized(self) -> bool: ...

    @property
    def model_key(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed document texts (applies document_prefix when configured)."""
        ...

    def embed_queries(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed query texts (applies query_prefix when configured)."""
        ...

    def close(self) -> None:
        """Release provider-owned resources. Idempotent."""
        ...
