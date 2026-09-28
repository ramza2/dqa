"""Factory for constructing the configured LLM provider."""

from __future__ import annotations

from app.adapters.llm.base import LLMProvider
from app.adapters.llm.errors import LLMProviderError, LLMProviderErrorCode
from app.adapters.llm.openai_compatible import OpenAICompatibleLLMProvider
from app.core.config import Settings


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Build the OpenAI-compatible provider from settings.

    Application startup must succeed without LLM settings. Completeness is
    checked only when a provider is actually constructed for use.
    """
    base_url = (settings.llm_base_url or "").strip()
    model = (settings.llm_model or "").strip()

    if not base_url:
        raise LLMProviderError(
            LLMProviderErrorCode.NOT_CONFIGURED,
            "LLM base URL is not configured",
        )
    if not model:
        raise LLMProviderError(
            LLMProviderErrorCode.NOT_CONFIGURED,
            "LLM model is not configured",
        )

    return OpenAICompatibleLLMProvider(
        base_url=base_url,
        model=model,
        api_key=settings.llm_api_key,
        timeout_seconds=settings.llm_timeout_seconds,
        connect_timeout_seconds=settings.llm_connect_timeout_seconds,
        enable_thinking=settings.llm_enable_thinking,
    )
