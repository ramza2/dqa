"""Provider-independent LLM message and structured-result schemas."""

from __future__ import annotations

from enum import Enum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)


class LLMRequestPurpose(str, Enum):
    """Explicit call purpose for routing / future audit metadata.

    RESULT_SUMMARIZATION is intentionally omitted: query-result rows must not be
    sent to an LLM until an approved data-egress policy exists.
    """

    TEMPLATE_RECOMMENDATION = "template_recommendation"
    PARAMETER_EXTRACTION = "parameter_extraction"
    CATALOG_EXPLANATION = "catalog_explanation"


class LLMMessage(BaseModel):
    """Single chat message independent of any vendor wire format."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class LLMUsage(BaseModel):
    """Optional token-usage metadata from a provider response."""

    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class LLMStructuredResult(BaseModel, Generic[T]):
    """Validated structured result returned to application services.

    Does not carry raw provider bodies, Authorization headers, API keys,
    or the original prompt/messages.
    """

    model_config = ConfigDict(extra="forbid")

    data: T
    provider: str
    model: str
    finish_reason: str | None = None
    usage: LLMUsage | None = None
    provider_request_id: str | None = None
