"""Typed errors for the LLM provider adapter boundary."""

from __future__ import annotations


class LLMProviderErrorCode:
    """Stable machine-readable codes (never embed secrets or prompt bodies)."""

    NOT_CONFIGURED = "LLM_PROVIDER_NOT_CONFIGURED"
    TIMEOUT = "LLM_PROVIDER_TIMEOUT"
    CONNECTION_ERROR = "LLM_PROVIDER_CONNECTION_ERROR"
    HTTP_ERROR = "LLM_PROVIDER_HTTP_ERROR"
    INVALID_RESPONSE = "LLM_PROVIDER_INVALID_RESPONSE"
    STRUCTURED_OUTPUT_INVALID = "LLM_PROVIDER_STRUCTURED_OUTPUT_INVALID"


class LLMProviderError(Exception):
    """Sanitized provider failure. Messages must not include secrets or prompts."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"LLMProviderError(code={self.code!r}, status_code={self.status_code!r}, "
            f"message={str(self)!r})"
        )
