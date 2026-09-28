"""Deterministic LLM provider test double (no HTTP)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from app.adapters.llm.errors import LLMProviderError
from app.schemas.llm import (
    LLMMessage,
    LLMRequestPurpose,
    LLMStructuredResult,
    LLMUsage,
)

T = TypeVar("T", bound=BaseModel)


@dataclass
class RecordedLLMCall:
    """Inspection record for a stubbed generate_structured invocation."""

    messages: list[LLMMessage]
    purpose: LLMRequestPurpose
    response_model: type[BaseModel]
    temperature: float
    max_tokens: int | None


@dataclass
class StubLLMProvider:
    """Configurable fake provider for unit tests."""

    result: LLMStructuredResult[Any] | None = None
    error: LLMProviderError | None = None
    calls: list[RecordedLLMCall] = field(default_factory=list)
    closed: bool = False

    def generate_structured(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[T],
        purpose: LLMRequestPurpose,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMStructuredResult[T]:
        self.calls.append(
            RecordedLLMCall(
                messages=list(messages),
                purpose=purpose,
                response_model=response_model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        )
        if self.error is not None:
            raise self.error
        if self.result is None:
            raise LLMProviderError(
                "LLM_PROVIDER_INVALID_RESPONSE",
                "StubLLMProvider has no configured result",
            )
        # Caller expects LLMStructuredResult[T]; tests configure a matching data type.
        return self.result  # type: ignore[return-value]

    def close(self) -> None:
        self.closed = True


def make_structured_result(
    data: T,
    *,
    provider: str = "stub",
    model: str = "stub-model",
    finish_reason: str | None = "stop",
    usage: LLMUsage | None = None,
    provider_request_id: str | None = None,
) -> LLMStructuredResult[T]:
    """Helper to build a typed stub result."""
    return LLMStructuredResult[T](
        data=data,
        provider=provider,
        model=model,
        finish_reason=finish_reason,
        usage=usage,
        provider_request_id=provider_request_id,
    )
