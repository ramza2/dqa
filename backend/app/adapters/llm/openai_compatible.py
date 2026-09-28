"""OpenAI-compatible Chat Completions LLM provider (httpx)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from app.adapters.llm.errors import LLMProviderError, LLMProviderErrorCode
from app.schemas.llm import (
    LLMMessage,
    LLMRequestPurpose,
    LLMStructuredResult,
    LLMUsage,
)

T = TypeVar("T", bound=BaseModel)

_PROVIDER_NAME = "openai_compatible"


def normalize_chat_completions_url(base_url: str) -> str:
    """Build ``.../v1/chat/completions`` without duplicating ``/v1``.

    Accepts ``https://host`` or ``https://host/v1`` (optional trailing slash).
    """
    trimmed = base_url.strip().rstrip("/")
    if not trimmed:
        raise LLMProviderError(
            LLMProviderErrorCode.NOT_CONFIGURED,
            "LLM base URL is not configured",
        )
    if trimmed.endswith("/v1"):
        return f"{trimmed}/chat/completions"
    return f"{trimmed}/v1/chat/completions"


class OpenAICompatibleLLMProvider:
    """OpenAI-compatible Chat Completions client using httpx.

    Does not log prompts, response bodies, or API keys. Does not retry.
    Structured output is strict JSON + Pydantic validation (no fence stripping).
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: SecretStr | str | None = None,
        timeout_seconds: float = 60.0,
        connect_timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        model_stripped = model.strip() if isinstance(model, str) else ""
        if not model_stripped:
            raise LLMProviderError(
                LLMProviderErrorCode.NOT_CONFIGURED,
                "LLM model is not configured",
            )
        self._endpoint = normalize_chat_completions_url(base_url)
        self._model = model_stripped
        self._api_key = _optional_secret(api_key)
        self._owns_client = client is None
        self._closed = False
        timeout = httpx.Timeout(
            timeout_seconds,
            connect=connect_timeout_seconds,
        )
        if client is not None:
            self._client = client
        else:
            self._client = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> OpenAICompatibleLLMProvider:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def generate_structured(
        self,
        *,
        messages: Sequence[LLMMessage],
        response_model: type[T],
        purpose: LLMRequestPurpose,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMStructuredResult[T]:
        # purpose reserved for future audit / routing; unused in wire payload.
        _ = purpose
        payload = self._build_payload(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        response = self._post(payload)
        envelope = self._parse_envelope(response)
        content = self._extract_content(envelope)
        data = self._validate_structured(content, response_model)
        return LLMStructuredResult[T](
            data=data,
            provider=_PROVIDER_NAME,
            model=self._resolve_model(envelope),
            finish_reason=self._optional_str(envelope.get("finish_reason")),
            usage=self._parse_usage(envelope.get("usage")),
            provider_request_id=self._optional_request_id(response),
        )

    def _build_payload(
        self,
        *,
        messages: Sequence[LLMMessage],
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        if not messages:
            raise LLMProviderError(
                LLMProviderErrorCode.INVALID_RESPONSE,
                "LLM request messages must not be empty",
            )
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        try:
            response = self._client.post(
                self._endpoint,
                headers=self._headers(),
                json=payload,
            )
        except httpx.TimeoutException:
            # from None: do not chain transport details into outer traceback.
            raise LLMProviderError(
                LLMProviderErrorCode.TIMEOUT,
                "LLM provider request timed out",
            ) from None
        except httpx.NetworkError:
            raise LLMProviderError(
                LLMProviderErrorCode.CONNECTION_ERROR,
                "LLM provider connection failed",
            ) from None
        except httpx.HTTPError:
            raise LLMProviderError(
                LLMProviderErrorCode.CONNECTION_ERROR,
                "LLM provider transport error",
            ) from None

        if response.status_code < 200 or response.status_code >= 300:
            raise LLMProviderError(
                LLMProviderErrorCode.HTTP_ERROR,
                f"LLM provider returned HTTP {response.status_code}",
                status_code=response.status_code,
            )
        return response

    def _parse_envelope(self, response: httpx.Response) -> dict[str, Any]:
        try:
            body: Any = response.json()
        except (json.JSONDecodeError, ValueError):
            # from None: raw body fragments must not appear in chained causes.
            raise LLMProviderError(
                LLMProviderErrorCode.INVALID_RESPONSE,
                "LLM provider returned non-JSON response body",
            ) from None
        if not isinstance(body, dict):
            raise LLMProviderError(
                LLMProviderErrorCode.INVALID_RESPONSE,
                "LLM provider response must be a JSON object",
            )

        choices = body.get("choices")
        if not isinstance(choices, list):
            raise LLMProviderError(
                LLMProviderErrorCode.INVALID_RESPONSE,
                "LLM provider response is missing choices",
            )
        if len(choices) == 0:
            raise LLMProviderError(
                LLMProviderErrorCode.INVALID_RESPONSE,
                "LLM provider response choices is empty",
            )
        first = choices[0]
        if not isinstance(first, dict):
            raise LLMProviderError(
                LLMProviderErrorCode.INVALID_RESPONSE,
                "LLM provider choice entry is invalid",
            )
        message = first.get("message")
        if not isinstance(message, dict):
            raise LLMProviderError(
                LLMProviderErrorCode.INVALID_RESPONSE,
                "LLM provider response is missing message",
            )
        return {
            "model": body.get("model"),
            "usage": body.get("usage"),
            "finish_reason": first.get("finish_reason"),
            "message": message,
            "id": body.get("id"),
        }

    def _extract_content(self, envelope: dict[str, Any]) -> str:
        message = envelope["message"]
        content = message.get("content")
        if not isinstance(content, str):
            raise LLMProviderError(
                LLMProviderErrorCode.INVALID_RESPONSE,
                "LLM provider message content must be a string",
            )
        return content

    def _validate_structured(self, content: str, response_model: type[T]) -> T:
        # Fail closed: no markdown-fence stripping, no prose repair, no regex extract.
        # strict=True rejects JSON type coercion (e.g. "10" -> int).
        # from None: ValidationError may embed rejected input_value in its repr.
        try:
            return response_model.model_validate_json(content, strict=True)
        except (ValidationError, ValueError, json.JSONDecodeError):
            raise LLMProviderError(
                LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID,
                "LLM provider structured output failed schema validation",
            ) from None

    def _resolve_model(self, envelope: dict[str, Any]) -> str:
        raw = envelope.get("model")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        return self._model

    def _parse_usage(self, raw: Any) -> LLMUsage | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            return None
        return LLMUsage(
            prompt_tokens=_optional_int(raw.get("prompt_tokens")),
            completion_tokens=_optional_int(raw.get("completion_tokens")),
            total_tokens=_optional_int(raw.get("total_tokens")),
        )

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None

    @staticmethod
    def _optional_request_id(response: httpx.Response) -> str | None:
        header = response.headers.get("x-request-id") or response.headers.get(
            "X-Request-Id"
        )
        if isinstance(header, str) and header.strip():
            return header.strip()
        return None


def _optional_secret(api_key: SecretStr | str | None) -> str | None:
    if api_key is None:
        return None
    if isinstance(api_key, SecretStr):
        value = api_key.get_secret_value()
    else:
        value = api_key
    stripped = value.strip()
    return stripped or None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None
