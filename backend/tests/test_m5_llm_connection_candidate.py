"""M5-L1B: pure server-side candidate policy, default deny and no egress."""

from __future__ import annotations

import pytest

from app.services.llm_connection_candidate import assess_llm_connection_candidate

ENDPOINT = "https://llm.example.invalid/v1"
ALLOWED = (ENDPOINT,)


def candidate(**changes: object) -> dict[str, object]:
    result: dict[str, object] = {
        "name": "internal gateway",
        "environment": "modelops",
        "protocol": "openai_compatible",
        "baseUrl": ENDPOINT,
        "modelId": "qwen3-14b",
        "timeoutSeconds": 60,
    }
    result.update(changes)
    return result


def decision(payload: dict[str, object], *, allowed=ALLOWED):
    return assess_llm_connection_candidate(payload, allowed_base_urls=allowed)


def test_provider_types_are_independent_of_api_protocol() -> None:
    for environment in ("modelops", "snuh_ai", "self_hosted", "other"):
        result = decision(candidate(environment=environment))
        assert result.code == "POLICY_REVIEW_REQUIRED"
        assert result.ready_for_runtime is False
        assert result.ready_for_connection_test is False
        assert result.server_configuration_changed is False
        assert result.credential_loaded is False


def test_no_allowlist_means_no_approval_or_egress() -> None:
    result = decision(candidate(), allowed=())
    assert result.code == "ENDPOINT_NOT_ALLOWLISTED"
    assert result.ready_for_runtime is False
    assert result.ready_for_connection_test is False


def test_unsupported_api_requires_an_explicit_adapter() -> None:
    result = decision(candidate(protocol="custom_api"))
    assert result.code == "UNSUPPORTED_ADAPTER"
    assert result.ready_for_runtime is False


@pytest.mark.parametrize("unsafe", [
    "http://127.0.0.1:8000/v1",
    "http://llm.example.invalid/v1",
])
def test_non_https_fails_closed(unsafe: str) -> None:
    assert decision(candidate(baseUrl=unsafe)).code == "INSECURE_ENDPOINT"


@pytest.mark.parametrize("unsafe", [
    "https://user:password@llm.example.invalid/v1",
    "https://llm.example.invalid/v1?token=hidden",
    "https://llm.example.invalid/v1#fragment",
    "https://llm.example.invalid/v1/%2e%2e",
    "https://llm.example.invalid/v1/../models",
    "https://llm.example.invalid//v1",
    "https://llm.example.invalid:invalid/v1",
    "https://llm.example.invalid/v1\\other",
    "https://llm.example.invalid/v1\nX-Test: secret",
    "not-a-url",
])
def test_ambiguous_and_credential_urls_fail_closed(unsafe: str) -> None:
    result = decision(candidate(baseUrl=unsafe), allowed=(unsafe,))
    assert result.code in {"INVALID_ENDPOINT", "INSECURE_ENDPOINT"}


@pytest.mark.parametrize("mismatch", [
    "https://llm.example.invalid.evil/v1",
    "https://other.example.invalid/v1",
    "https://llm.example.invalid:8443/v1",
    "https://llm.example.invalid/v2",
])
def test_approved_endpoint_must_be_exact(mismatch: str) -> None:
    assert decision(candidate(baseUrl=mismatch)).code == "ENDPOINT_NOT_ALLOWLISTED"


@pytest.mark.parametrize("invalid", [
    {"name": ""},
    {"modelId": ""},
    {"timeoutSeconds": 0},
    {"timeoutSeconds": 301},
    {"timeoutSeconds": "60"},
    {"environment": "huggingface_api"},
    {"protocol": "auto"},
    {"api_key": "test-secret"},
    {"prompt": "patient-query"},
    {"enabled": True},
    {"raw_request_egress_approved": True},
])
def test_invalid_fields_or_unexpected_privilege_requests_rejected(invalid: dict) -> None:
    assert decision(candidate(**invalid)).code == "INVALID_FIELDS"


def test_all_results_are_secret_and_host_free() -> None:
    cases = [
        candidate(baseUrl="https://secret-user:secret-key@llm.example.invalid/v1"),
        candidate(baseUrl="https://llm.example.invalid/v1?token=secret-key"),
        candidate(),
    ]
    for item in cases:
        outcome = decision(item)
        output = outcome.model_dump_json() + repr(outcome)
        assert "llm.example.invalid" not in output
        assert "secret-key" not in output
        assert "secret-user" not in output
        assert "qwen3-14b" not in output


def test_allowed_endpoint_trailing_slash_only_normalization() -> None:
    assert decision(candidate(baseUrl=ENDPOINT + "/")).code == "POLICY_REVIEW_REQUIRED"
    assert decision(candidate(), allowed=(ENDPOINT + "/",)).code == "POLICY_REVIEW_REQUIRED"
