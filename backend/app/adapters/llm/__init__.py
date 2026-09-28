"""LLM provider adapter package.

Transport boundary only: OpenAI-compatible Chat Completions via httpx.
Does not recommend templates, extract parameters, generate SQL, or execute queries.
Does not expose a public chat API. Query-result rows must not be sent to an LLM.
"""

from app.adapters.llm.base import LLMProvider
from app.adapters.llm.errors import LLMProviderError, LLMProviderErrorCode
from app.adapters.llm.factory import create_llm_provider
from app.adapters.llm.openai_compatible import (
    OpenAICompatibleLLMProvider,
    normalize_chat_completions_url,
)

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "LLMProviderErrorCode",
    "OpenAICompatibleLLMProvider",
    "create_llm_provider",
    "normalize_chat_completions_url",
]
