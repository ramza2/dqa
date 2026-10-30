"""M5-S0: secret-safe admin integration inventory contract tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.errors import AuthErrorCode
from app.core.config import get_settings

PATH = "/api/v1/admin/integration-settings"


def _headers(role: str) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": "m5-user",
        "X-DQA-Dev-Roles": role,
    }


def test_default_inventory_is_read_only_and_denies_external_service_management(
    client: TestClient,
) -> None:
    response = client.get(PATH)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "llm": {
            "provider": "openai_compatible",
            "endpoint_configured": False,
            "model_configured": False,
            "model": None,
            "api_key_present": False,
            "raw_request_egress_allowed": False,
        },
        "external_service": {
            "service_client_management_available": False,
            "managed_service_authentication_available": False,
        },
        "editable": False,
    }
    assert client.post(PATH, json={"enabled": True}).status_code == 405


def test_inventory_hides_secrets_and_urls(
    client: TestClient, monkeypatch,
) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://private-host.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "approved-model")
    monkeypatch.setenv("LLM_API_KEY", "sensitive-api-key-never-return")
    monkeypatch.setenv("LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST", "true")
    # Technical opt-in without separate approval cannot allow egress.
    monkeypatch.setenv("LLM_PARAMETER_EXTRACTION_RAW_REQUEST_EGRESS_APPROVED", "false")
    get_settings.cache_clear()
    try:
        response = client.get(PATH)
        assert response.status_code == 200
        body = response.json()
        assert body["llm"]["model"] == "approved-model"
        assert body["llm"]["endpoint_configured"] is True
        assert body["llm"]["api_key_present"] is True
        assert body["llm"]["raw_request_egress_allowed"] is False
        assert "private-host.invalid" not in response.text
        assert "sensitive-api-key-never-return" not in response.text
    finally:
        get_settings.cache_clear()


def test_inventory_is_admin_only(unauth_client: TestClient) -> None:
    denied = unauth_client.get(PATH, headers=_headers("query_operator"))
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED

    missing = unauth_client.get(PATH)
    assert missing.status_code == 401
    assert missing.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED

    permitted = unauth_client.get(PATH, headers=_headers("administrator"))
    assert permitted.status_code == 200


def test_inventory_fails_closed_without_provider(
    unauth_client: TestClient, monkeypatch,
) -> None:
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "disabled")
    get_settings.cache_clear()
    try:
        denied = unauth_client.get(PATH, headers=_headers("administrator"))
        assert denied.status_code == 503
        assert denied.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    finally:
        get_settings.cache_clear()
