"""M5-L0: development-only model-list probe and authorization guard."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.auth.errors import AuthErrorCode
from app.core.config import Settings, get_settings
from app.services.llm_connection_probe import (
    LLMConnectionTestResult,
    llm_connection_test_available,
    probe_configured_llm,
)

PATH = "/api/v1/admin/integration-settings/llm/test"


def _settings(**overrides: str) -> Settings:
    values = {
        "APP_ENV": "test",
        "LLM_BASE_URL": "https://llm.example.invalid/v1",
        "LLM_MODEL": "test-model",
        "LLM_API_KEY": "private-token-never-echo",
        "DQA_DEV_LLM_CONNECTION_TEST_ENABLED": "true",
        "DQA_DEV_LLM_CONNECTION_TEST_ALLOWED_BASE_URL": "https://llm.example.invalid/v1",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_off_by_default_and_exact_allowlist() -> None:
    assert not llm_connection_test_available(
        _settings(DQA_DEV_LLM_CONNECTION_TEST_ENABLED="false")
    )
    assert not llm_connection_test_available(
        _settings(DQA_DEV_LLM_CONNECTION_TEST_ALLOWED_BASE_URL="https://other.invalid/v1")
    )
    assert not llm_connection_test_available(_settings(APP_ENV="production"))
    assert not llm_connection_test_available(
        _settings(LLM_BASE_URL="http://llm.example.invalid/v1",
                  DQA_DEV_LLM_CONNECTION_TEST_ALLOWED_BASE_URL="http://llm.example.invalid/v1")
    )
    assert not llm_connection_test_available(
        _settings(LLM_BASE_URL="https://user:password@llm.example.invalid/v1",
                  DQA_DEV_LLM_CONNECTION_TEST_ALLOWED_BASE_URL="https://user:password@llm.example.invalid/v1")
    )
    assert not llm_connection_test_available(
        _settings(LLM_BASE_URL="https://llm.example.invalid/v1?probe=1",
                  DQA_DEV_LLM_CONNECTION_TEST_ALLOWED_BASE_URL="https://llm.example.invalid/v1?probe=1")
    )
    assert llm_connection_test_available(_settings())


def test_nonclinical_get_only_and_secret_free_response() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={
            "object": "list",
            "data": [{"id": "test-model"}, {"id": "another-model"}],
        })

    result = probe_configured_llm(
        _settings(), transport=httpx.MockTransport(handler),
    )
    assert result.status == "CONNECTED"
    assert result.http_status == 200
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert str(requests[0].url) == "https://llm.example.invalid/v1/models"
    assert requests[0].content == b""
    assert requests[0].headers["Authorization"] == "Bearer private-token-never-echo"
    assert "private-token" not in result.model_dump_json()
    assert "llm.example.invalid" not in result.model_dump_json()


def test_missing_model_redirect_and_invalid_provider_response() -> None:
    missing = probe_configured_llm(
        _settings(),
        transport=httpx.MockTransport(
            lambda _req: httpx.Response(200, json={"data": [{"id": "other"}]})
        ),
    )
    assert missing.status == "MODEL_NOT_FOUND"

    seen = []
    def redirect(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://untrusted.invalid/v1/models"})
    result = probe_configured_llm(
        _settings(), transport=httpx.MockTransport(redirect),
    )
    assert result.status == "HTTP_ERROR"
    assert result.http_status == 302
    assert len(seen) == 1  # no redirects followed

    invalid = probe_configured_llm(
        _settings(),
        transport=httpx.MockTransport(lambda _req: httpx.Response(
            200, content=b"patient-id-never-echo",
        )),
    )
    assert invalid.status == "INVALID_RESPONSE"
    assert "patient" not in invalid.model_dump_json()


def test_probe_timeout_and_unconfigured_fail_closed() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("private-host-never-echo")
    result = probe_configured_llm(
        _settings(), transport=httpx.MockTransport(timeout),
    )
    assert result.status == "TIMEOUT"
    assert "private-host" not in result.model_dump_json()

    try:
        probe_configured_llm(
            _settings(DQA_DEV_LLM_CONNECTION_TEST_ENABLED="false"),
            transport=httpx.MockTransport(timeout),
        )
    except ValueError:
        pass
    else:
        raise AssertionError("disabled probe must refuse network")


def test_probe_api_disabled_by_default(
    client: TestClient,
) -> None:
    response = client.post(PATH, json={})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LLM_CONNECTION_TEST_DISABLED"


def test_probe_api_requires_admin(unauth_client: TestClient) -> None:
    denied = unauth_client.post(
        PATH, json={},
        headers={"X-DQA-Dev-Actor": "operator", "X-DQA-Dev-Roles": "query_operator"},
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED
    anonymous = unauth_client.post(PATH, json={})
    assert anonymous.status_code == 401


def test_probe_api_uses_configured_target_only(
    client: TestClient, monkeypatch,
) -> None:
    for name, value in {
        "LLM_BASE_URL": "https://llm.example.invalid/v1",
        "LLM_MODEL": "test-model",
        "DQA_DEV_LLM_CONNECTION_TEST_ENABLED": "true",
        "DQA_DEV_LLM_CONNECTION_TEST_ALLOWED_BASE_URL": "https://llm.example.invalid/v1",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    from app.api.routes import integration_settings as route

    seen = []
    def fake_probe(settings: Settings) -> LLMConnectionTestResult:
        seen.append(settings.llm_base_url)
        return LLMConnectionTestResult(status="CONNECTED", http_status=200)

    monkeypatch.setattr(route, "probe_configured_llm", fake_probe)
    try:
        response = client.post(PATH, json={})
        assert response.status_code == 200
        assert response.json() == {"status": "CONNECTED", "http_status": 200}
        assert seen == ["https://llm.example.invalid/v1"]
        # Arbitrary target submitted by caller never overrides the configured URL.
        response = client.post(PATH, json={"base_url": "https://untrusted.invalid"})
        assert response.status_code == 200
        assert seen == ["https://llm.example.invalid/v1"] * 2
    finally:
        get_settings.cache_clear()
