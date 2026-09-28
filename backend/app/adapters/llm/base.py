"""Vendor-independent LLM provider protocol."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar

from pydantic import BaseModel

from app.schemas.llm import LLMMessage, LLMRequestPurpose, LLMStructuredResult

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    """Application-facing LLM boundary.

    Implementations hide HTTP transport and vendor JSON envelopes. Callers supply
    a Pydantic response model and receive a validated typed result only.
    """

    def generate_structured(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[T],
        purpose: LLMRequestPurpose,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMStructuredResult[T]:
        """Request a structured JSON response and validate it as ``response_model``.

        ``purpose`` is metadata for routing / future audit; it is not sent to a
        public API in this PR.
        """
        ...

    def close(self) -> None:
        """Release provider-owned resources (e.g. HTTP client). Idempotent."""
        ...
