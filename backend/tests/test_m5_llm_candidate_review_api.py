"""M5-L1C: dev-only stateless candidate review API authorization and egress gates."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.auth.errors import AuthErrorCode
from app.core.config import Settings, get_settings
from app.api.routes.integration_settings import llm_candidate_review_available

PATH = "/api/v1/admin/integration-settings/llm-candidate/review"
STATUS = "/api/v1/admin/integration-settings"
PIN = "https://candidate.example.invalid/v1"


def candidate(**changes: object) -> dict[str, object]:
    item: dict[str, object] = {
        "name": "연구용 내부 모델",
        "environment": "modelops",
        "protocol": "openai_compatible",
        "baseUrl": PIN,
        "modelId": "Qwen/Qwen3-14B-AWQ",
        "timeoutSeconds": 60,
    }
    item.update(changes)
    return item


@pytest.fixture()
def review_client(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Explicitly enable a test-environment, admin-only, pinned review."""
    monkeypatch.setenv("DQA_DEV_LLM_CANDIDATE_REVIEW_ENABLED", "true")
    monkeypatch.setenv("DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL", PIN)
    get_settings.cache_clear()
    try:
        yield client
    finally:
        get_settings.cache_clear()


def test_review_is_disabled_by_default(client: TestClient) -> None:
    response = client.post(PATH, json=candidate())
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LLM_CANDIDATE_REVIEW_DISABLED"
    assert "candidate.example.invalid" not in response.text
    assert client.get(STATUS).json()["llm"]["candidate_review_available"] is False


def test_review_requires_explicit_flag_pin_and_development_environment() -> None:
    values = {
        "APP_ENV": "development",
        "DQA_DEV_LLM_CANDIDATE_REVIEW_ENABLED": "true",
        "DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL": PIN,
    }
    assert llm_candidate_review_available(Settings(_env_file=None, **values))
    for key, bad in (
        ("APP_ENV", "production"),
        ("APP_ENV", "staging"),
        ("DQA_DEV_LLM_CANDIDATE_REVIEW_ENABLED", "false"),
        ("DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL", ""),
        ("DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL", "http://candidate.example.invalid/v1"),
        ("DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL", "https://user:pass@candidate.example.invalid/v1"),
    ):
        case = dict(values)
        case[key] = bad
        assert not llm_candidate_review_available(Settings(_env_file=None, **case))


def test_review_sanitized_success_and_status_capability(
    review_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.routes import integration_settings as route

    def unexpected_probe(*_args, **_kwargs):
        raise AssertionError("Candidate review must never contact provider")

    monkeypatch.setattr(route, "probe_configured_llm", unexpected_probe)
    response = review_client.post(PATH, json=candidate())
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "code": "POLICY_REVIEW_REQUIRED",
        "server_configuration_changed": False,
        "credential_loaded": False,
        "ready_for_runtime": False,
        "ready_for_connection_test": False,
    }
    assert "candidate.example.invalid" not in response.text
    assert "Qwen" not in response.text
    assert review_client.get(STATUS).json()["llm"]["candidate_review_available"] is True


@pytest.mark.parametrize("diff,expected", [
    ({"baseUrl": "https://other.example.invalid/v1"}, "ENDPOINT_NOT_ALLOWLISTED"),
    ({"baseUrl": "http://candidate.example.invalid/v1"}, "INSECURE_ENDPOINT"),
    ({"baseUrl": "https://candidate.example.invalid/v1?secret=forbidden"}, "INVALID_ENDPOINT"),
    ({"protocol": "custom_api"}, "UNSUPPORTED_ADAPTER"),
    ({"api_key": "never-echo-secret"}, "INVALID_FIELDS"),
    ({"enabled": True}, "INVALID_FIELDS"),
    ({"timeoutSeconds": "60"}, "INVALID_FIELDS"),
])
def test_candidate_review_denial_cases(
    review_client: TestClient, diff: dict[str, object], expected: str
) -> None:
    response = review_client.post(PATH, json=candidate(**diff))
    assert response.status_code == 200
    assert response.json()["code"] == expected
    assert response.json()["ready_for_runtime"] is False
    assert "candidate.example.invalid" not in response.text
    assert "never-echo-secret" not in response.text


def test_review_requires_admin_even_with_feature_enabled(
    unauth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DQA_DEV_LLM_CANDIDATE_REVIEW_ENABLED", "true")
    monkeypatch.setenv("DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL", PIN)
    get_settings.cache_clear()
    try:
        denied = unauth_client.post(
            PATH,
            json=candidate(),
            headers={
                "X-DQA-Dev-Actor": "non-admin",
                "X-DQA-Dev-Roles": "query_operator",
            },
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED
        missing = unauth_client.post(PATH, json=candidate())
        assert missing.status_code == 401
        assert missing.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED
    finally:
        get_settings.cache_clear()


def test_prod_auth_provider_disabled_still_refuses_review(
    unauth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "disabled")
    monkeypatch.setenv("DQA_DEV_LLM_CANDIDATE_REVIEW_ENABLED", "true")
    monkeypatch.setenv("DQA_DEV_LLM_CANDIDATE_REVIEW_ALLOWED_BASE_URL", PIN)
    get_settings.cache_clear()
    try:
        denied = unauth_client.post(
            PATH,
            json=candidate(),
            headers={"X-DQA-Dev-Actor": "admin", "X-DQA-Dev-Roles": "administrator"},
        )
        assert denied.status_code == 503
        assert denied.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    finally:
        get_settings.cache_clear()


def test_bounded_body_and_json_media_type(review_client: TestClient) -> None:
    too_large = json.dumps(candidate(name="x" * 5000))
    blocked = review_client.post(
        PATH, content=too_large, headers={"content-type": "application/json"},
    )
    assert blocked.status_code == 413
    assert blocked.json()["detail"]["code"] == "CANDIDATE_BODY_TOO_LARGE"

    wrong_type = review_client.post(
        PATH, content="{}",
        headers={"content-type": "text/plain"},
    )
    assert wrong_type.status_code == 415
    assert wrong_type.json()["detail"]["code"] == "JSON_BODY_REQUIRED"

    malformed = review_client.post(
        PATH, content='{"name":', headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 200
    assert malformed.json()["code"] == "INVALID_FIELDS"


def test_json_duplicate_keys_and_non_object_are_rejected(
    review_client: TestClient
) -> None:
    duplicate = b'{"name":"A","name":"B"}'
    response = review_client.post(
        PATH, content=duplicate, headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["code"] == "INVALID_FIELDS"

    non_object = review_client.post(PATH, json=[candidate()])
    assert non_object.status_code == 200
    assert non_object.json()["code"] == "INVALID_FIELDS"


def test_review_has_no_get_or_mutation_surface(review_client: TestClient) -> None:
    assert review_client.get(PATH).status_code == 405
    assert review_client.put(PATH, json=candidate()).status_code == 405
    assert review_client.delete(PATH).status_code == 405
