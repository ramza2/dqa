"""Focused LLM provider abstraction tests (no external network)."""

from __future__ import annotations

import json
import traceback
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr, ValidationError

from app.adapters.llm import (
    LLMProvider,
    LLMProviderError,
    LLMProviderErrorCode,
    OpenAICompatibleLLMProvider,
    create_llm_provider,
    normalize_chat_completions_url,
)
from app.core.config import Settings, get_settings
from app.schemas.llm import LLMMessage, LLMRequestPurpose, LLMUsage
from tests.fakes.llm import StubLLMProvider, make_structured_result


class ExampleRecommendation(BaseModel):
    selected_template_id: int
    confidence: float


class ExampleFlag(BaseModel):
    enabled: bool


SECRET_KEY = "sk-test-secret-do-not-leak"
LEAK_MARKER = "DO_NOT_LEAK_12345"


def _settings(**overrides: Any) -> Settings:
    base = {
        "APP_ENV": "test",
        "DQA_DB_HOST": "localhost",
        "DQA_DB_PORT": 5432,
        "DQA_DB_NAME": "dqa",
        "DQA_DB_USER": "dqa",
        "DQA_DB_PASSWORD": "change-me",
        "LLM_BASE_URL": None,
        "LLM_API_KEY": None,
        "LLM_MODEL": None,
        "LLM_TIMEOUT_SECONDS": 60.0,
        "LLM_CONNECT_TIMEOUT_SECONDS": 10.0,
    }
    base.update(overrides)
    return Settings(**base)


def _success_body(
    *,
    content: str,
    model: str = "demo-model",
    finish_reason: str = "stop",
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "chatcmpl-test",
        "model": model,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {"role": "assistant", "content": content},
            }
        ],
    }
    if usage is not None:
        body["usage"] = usage
    return body


def _provider_with_handler(
    handler,
    *,
    base_url: str = "https://llm.example",
    model: str = "demo-model",
    api_key: str | None = SECRET_KEY,
) -> OpenAICompatibleLLMProvider:
    transport = httpx.MockTransport(handler)
    return OpenAICompatibleLLMProvider(
        base_url=base_url,
        model=model,
        api_key=api_key,
        transport=transport,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def test_settings_without_llm_succeeds() -> None:
    settings = _settings()
    assert settings.llm_base_url is None
    assert settings.llm_model is None
    assert settings.llm_api_key is None
    assert settings.llm_timeout_seconds == 60.0
    assert settings.llm_connect_timeout_seconds == 10.0


def test_settings_llm_defaults_from_env(test_settings_env: dict[str, str]) -> None:
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.llm_base_url in (None, "")
        assert settings.llm_model in (None, "")
    finally:
        get_settings.cache_clear()


def test_factory_missing_base_url_raises() -> None:
    with pytest.raises(LLMProviderError) as exc_info:
        create_llm_provider(_settings(LLM_MODEL="demo-model"))
    assert exc_info.value.code == LLMProviderErrorCode.NOT_CONFIGURED
    assert SECRET_KEY not in str(exc_info.value)


def test_factory_missing_model_raises() -> None:
    with pytest.raises(LLMProviderError) as exc_info:
        create_llm_provider(_settings(LLM_BASE_URL="https://llm.example"))
    assert exc_info.value.code == LLMProviderErrorCode.NOT_CONFIGURED


def test_factory_builds_openai_compatible_provider() -> None:
    provider = create_llm_provider(
        _settings(
            LLM_BASE_URL="https://llm.example/v1",
            LLM_MODEL="demo-model",
            LLM_API_KEY=SECRET_KEY,
        )
    )
    assert isinstance(provider, OpenAICompatibleLLMProvider)
    provider.close()


def test_api_key_empty_omits_authorization_header() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json=_success_body(
                content='{"selected_template_id": 1, "confidence": 0.5}'
            ),
        )

    provider = _provider_with_handler(handler, api_key="")
    provider.generate_structured(
        messages=[LLMMessage(role="user", content="hello")],
        response_model=ExampleRecommendation,
        purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
    )
    assert captured["authorization"] is None
    provider.close()


def test_api_key_present_sends_bearer() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json=_success_body(
                content='{"selected_template_id": 1, "confidence": 0.5}'
            ),
        )

    provider = _provider_with_handler(handler, api_key=SECRET_KEY)
    provider.generate_structured(
        messages=[LLMMessage(role="user", content="hello")],
        response_model=ExampleRecommendation,
        purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
    )
    assert captured["authorization"] == f"Bearer {SECRET_KEY}"
    provider.close()


def test_secret_str_and_error_do_not_expose_api_key() -> None:
    settings = _settings(
        LLM_BASE_URL="https://llm.example",
        LLM_MODEL="demo-model",
        LLM_API_KEY=SECRET_KEY,
    )
    assert isinstance(settings.llm_api_key, SecretStr)
    assert SECRET_KEY not in repr(settings.llm_api_key)
    assert SECRET_KEY not in str(settings.llm_api_key)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text=f"boom {SECRET_KEY}")

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="prompt with secret")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    err = exc_info.value
    assert err.code == LLMProviderErrorCode.HTTP_ERROR
    assert SECRET_KEY not in str(err)
    assert SECRET_KEY not in repr(err)
    assert "prompt with secret" not in str(err)
    assert "boom" not in str(err)
    provider.close()


# ---------------------------------------------------------------------------
# URL normalization / request shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "base,expected",
    [
        ("https://host", "https://host/v1/chat/completions"),
        ("https://host/", "https://host/v1/chat/completions"),
        ("https://host/v1", "https://host/v1/chat/completions"),
        ("https://host/v1/", "https://host/v1/chat/completions"),
    ],
)
def test_normalize_chat_completions_url(base: str, expected: str) -> None:
    assert normalize_chat_completions_url(base) == expected


def test_request_payload_and_endpoint() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            headers={"x-request-id": "req-123"},
            json=_success_body(
                content='{"selected_template_id": 10, "confidence": 0.91}',
                usage={"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            ),
        )

    provider = _provider_with_handler(handler, base_url="https://llm.example/v1")
    result = provider.generate_structured(
        messages=[
            LLMMessage(role="system", content="Return JSON only."),
            LLMMessage(role="user", content="Recommend a template."),
        ],
        response_model=ExampleRecommendation,
        purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        temperature=0.0,
        max_tokens=128,
    )
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    body = captured["body"]
    assert body["model"] == "demo-model"
    assert body["temperature"] == 0.0
    assert body["max_tokens"] == 128
    assert body["messages"] == [
        {"role": "system", "content": "Return JSON only."},
        {"role": "user", "content": "Recommend a template."},
    ]
    assert "tools" not in body
    assert "functions" not in body
    assert result.data.selected_template_id == 10
    assert result.data.confidence == 0.91
    assert result.provider == "openai_compatible"
    assert result.model == "demo-model"
    assert result.finish_reason == "stop"
    assert result.usage == LLMUsage(
        prompt_tokens=11, completion_tokens=7, total_tokens=18
    )
    assert result.provider_request_id == "req-123"
    provider.close()


def test_max_tokens_omitted_when_none() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json=_success_body(
                content='{"selected_template_id": 2, "confidence": 0.4}'
            ),
        )

    provider = _provider_with_handler(handler)
    provider.generate_structured(
        messages=[LLMMessage(role="user", content="x")],
        response_model=ExampleRecommendation,
        purpose=LLMRequestPurpose.PARAMETER_EXTRACTION,
    )
    assert "max_tokens" not in captured["body"]
    provider.close()


# ---------------------------------------------------------------------------
# Structured success / invalid structured output
# ---------------------------------------------------------------------------


def test_structured_success_without_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_body(
                content='{"selected_template_id": 3, "confidence": 0.2}',
                finish_reason="length",
            ),
        )

    provider = _provider_with_handler(handler)
    result = provider.generate_structured(
        messages=[LLMMessage(role="user", content="x")],
        response_model=ExampleRecommendation,
        purpose=LLMRequestPurpose.CATALOG_EXPLANATION,
    )
    assert result.usage is None
    assert result.finish_reason == "length"
    assert isinstance(result.data, ExampleRecommendation)
    provider.close()


def test_markdown_fenced_json_is_rejected() -> None:
    fenced = '```json\n{"selected_template_id": 10, "confidence": 0.9}\n```'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body(content=fenced))

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID
    provider.close()


def test_prose_wrapped_json_is_rejected() -> None:
    prose = 'Here you go: {"selected_template_id": 10, "confidence": 0.9}'

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body(content=prose))

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID
    provider.close()


def test_malformed_json_content_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body(content='{"selected_template_id":'))

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID
    provider.close()


def test_schema_mismatch_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_body(content='{"selected_template_id": "nope", "confidence": 1}'),
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID
    provider.close()


def test_structured_output_error_does_not_leak_model_content() -> None:
    content = json.dumps(
        {"selected_template_id": LEAK_MARKER, "confidence": 0.5}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body(content=content))

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    err = exc_info.value
    assert err.code == LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID
    assert LEAK_MARKER not in str(err)
    assert LEAK_MARKER not in repr(err)
    # raise ... from None: no explicit cause; context is suppressed in traceback.
    assert err.__cause__ is None
    assert err.__suppress_context__ is True
    formatted = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    assert LEAK_MARKER not in formatted
    assert "ValidationError" not in formatted
    provider.close()


def test_strict_json_types_accept_native_numbers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_body(
                content='{"selected_template_id": 10, "confidence": 0.91}'
            ),
        )

    provider = _provider_with_handler(handler)
    result = provider.generate_structured(
        messages=[LLMMessage(role="user", content="x")],
        response_model=ExampleRecommendation,
        purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
    )
    assert result.data.selected_template_id == 10
    assert result.data.confidence == 0.91
    provider.close()


@pytest.mark.parametrize(
    "content",
    [
        '{"selected_template_id": "10", "confidence": 0.91}',
        '{"selected_template_id": 10, "confidence": "0.91"}',
    ],
)
def test_strict_json_types_reject_coerced_strings(content: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body(content=content))

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID
    provider.close()


def test_strict_boolean_accepts_true_rejects_string_true() -> None:
    def ok_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body(content='{"enabled": true}'))

    provider = _provider_with_handler(ok_handler)
    result = provider.generate_structured(
        messages=[LLMMessage(role="user", content="x")],
        response_model=ExampleFlag,
        purpose=LLMRequestPurpose.CATALOG_EXPLANATION,
    )
    assert result.data.enabled is True
    provider.close()

    def bad_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_success_body(content='{"enabled": "true"}'))

    provider = _provider_with_handler(bad_handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleFlag,
            purpose=LLMRequestPurpose.CATALOG_EXPLANATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID
    provider.close()


# ---------------------------------------------------------------------------
# Transport / HTTP / envelope errors
# ---------------------------------------------------------------------------


def test_connect_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect timed out")

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.TIMEOUT
    provider.close()


def test_read_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.TIMEOUT
    provider.close()


def test_connection_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.CONNECTION_ERROR
    provider.close()


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_error_status(status: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="<html>error</html>")

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    err = exc_info.value
    assert err.code == LLMProviderErrorCode.HTTP_ERROR
    assert err.status_code == status
    assert f"HTTP {status}" in str(err)
    assert "<html>" not in str(err)
    provider.close()


def test_top_level_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not-json")

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.INVALID_RESPONSE
    provider.close()


def test_missing_choices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"model": "demo-model"})

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.INVALID_RESPONSE
    provider.close()


def test_empty_choices() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.INVALID_RESPONSE
    provider.close()


def test_missing_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop"}]})

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.INVALID_RESPONSE
    provider.close()


def test_missing_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant"}}]},
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.INVALID_RESPONSE
    provider.close()


def test_non_string_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"role": "assistant", "content": {"a": 1}}}
                ]
            },
        )

    provider = _provider_with_handler(handler)
    with pytest.raises(LLMProviderError) as exc_info:
        provider.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.INVALID_RESPONSE
    provider.close()


def test_model_fallback_when_response_omits_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"selected_template_id": 9, "confidence": 0.1}',
                        }
                    }
                ]
            },
        )

    provider = _provider_with_handler(handler, model="configured-model")
    result = provider.generate_structured(
        messages=[LLMMessage(role="user", content="x")],
        response_model=ExampleRecommendation,
        purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
    )
    assert result.model == "configured-model"
    provider.close()


# ---------------------------------------------------------------------------
# Stub / fake provider
# ---------------------------------------------------------------------------


def test_stub_returns_configured_result() -> None:
    data = ExampleRecommendation(selected_template_id=42, confidence=0.88)
    stub = StubLLMProvider(result=make_structured_result(data))
    result = stub.generate_structured(
        messages=[LLMMessage(role="user", content="find template")],
        response_model=ExampleRecommendation,
        purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        temperature=0.0,
        max_tokens=50,
    )
    assert result.data.selected_template_id == 42
    assert len(stub.calls) == 1
    assert stub.calls[0].purpose == LLMRequestPurpose.TEMPLATE_RECOMMENDATION
    assert stub.calls[0].messages[0].content == "find template"
    assert stub.calls[0].response_model is ExampleRecommendation
    assert stub.calls[0].max_tokens == 50


def test_stub_raises_configured_error() -> None:
    stub = StubLLMProvider(
        error=LLMProviderError(
            LLMProviderErrorCode.TIMEOUT,
            "LLM provider request timed out",
        )
    )
    with pytest.raises(LLMProviderError) as exc_info:
        stub.generate_structured(
            messages=[LLMMessage(role="user", content="x")],
            response_model=ExampleRecommendation,
            purpose=LLMRequestPurpose.PARAMETER_EXTRACTION,
        )
    assert exc_info.value.code == LLMProviderErrorCode.TIMEOUT
    assert len(stub.calls) == 1


def test_stub_close_records_lifecycle() -> None:
    stub = StubLLMProvider(
        result=make_structured_result(
            ExampleRecommendation(selected_template_id=1, confidence=0.1)
        )
    )
    assert stub.closed is False
    as_protocol: LLMProvider = stub
    as_protocol.close()
    assert stub.closed is True
    stub.close()
    assert stub.closed is True


def test_concrete_provider_close_is_idempotent() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_success_body(
                content='{"selected_template_id": 1, "confidence": 0.1}'
            ),
        )

    provider: LLMProvider = _provider_with_handler(handler)
    provider.close()
    provider.close()


def test_factory_created_provider_is_closeable() -> None:
    provider = create_llm_provider(
        _settings(
            LLM_BASE_URL="https://llm.example",
            LLM_MODEL="demo-model",
        )
    )
    as_protocol: LLMProvider = provider
    as_protocol.close()
    as_protocol.close()


def test_llm_message_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        LLMMessage(role="user", content="")


def test_result_summarization_purpose_not_defined() -> None:
    assert not hasattr(LLMRequestPurpose, "RESULT_SUMMARIZATION")
    names = {member.name for member in LLMRequestPurpose}
    assert names == {
        "TEMPLATE_RECOMMENDATION",
        "PARAMETER_EXTRACTION",
        "CATALOG_EXPLANATION",
    }
