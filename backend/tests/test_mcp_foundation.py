"""Phase 28-A: MCP server foundation (transport, auth, registry; no query tools)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.errors import AuthErrorCode
from app.core.config import get_settings
from app.mcp.adapter import McpApplicationAdapter
from app.mcp.registry import build_foundation_registry
from app.mcp.server import normalize_mcp_mount_path

pytestmark = pytest.mark.integration

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "X-DQA-Dev-Actor": "mcp-tester",
    "X-DQA-Dev-Roles": "viewer",
}


def _clear_caches() -> None:
    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


@pytest.fixture()
def mcp_env(monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]) -> dict[str, str]:
    monkeypatch.setenv("DQA_MCP_ENABLED", "true")
    monkeypatch.setenv("DQA_MCP_MOUNT_PATH", "/mcp")
    monkeypatch.setenv("DQA_MCP_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    monkeypatch.setenv("APP_ENV", "test")
    _clear_caches()
    return {"DQA_MCP_ENABLED": "true"}


@pytest.fixture()
def mcp_client(mcp_env: dict[str, str]) -> TestClient:
    from app.main import create_app

    _clear_caches()
    application = create_app(check_migrations_on_startup=False)
    with TestClient(application) as client:
        yield client
    _clear_caches()


def _mcp_post(
    client: TestClient,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
) -> Any:
    return client.post(
        "/mcp/",
        headers={**_MCP_HEADERS, **(headers or {})},
        json=payload,
    )


def test_normalize_mount_path() -> None:
    assert normalize_mcp_mount_path("/mcp") == "/mcp"
    assert normalize_mcp_mount_path("mcp/") == "/mcp"
    assert normalize_mcp_mount_path("") == "/mcp"


def test_foundation_registry_has_ready_only() -> None:
    registry = build_foundation_registry()
    names = registry.names()
    assert names == ["dqa.mcp_ready"]
    assert "demis.search_schema" not in names
    assert "demis.execute_query" not in names


def test_mcp_disabled_by_default(test_settings_env: dict[str, str]) -> None:
    from app.main import create_app

    _clear_caches()
    application = create_app(check_migrations_on_startup=False)
    with TestClient(application) as client:
        response = client.post(
            "/mcp/",
            headers=_MCP_HEADERS,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert response.status_code == 404
    _clear_caches()


def test_initialize_and_list_tools(mcp_client: TestClient) -> None:
    init = _mcp_post(
        mcp_client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dqa-test", "version": "0"},
            },
        },
    )
    assert init.status_code == 200
    body = init.json()
    assert body["result"]["serverInfo"]["name"] == "dqa-mcp"
    assert "tools" in body["result"]["capabilities"]

    listed = _mcp_post(
        mcp_client,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert listed.status_code == 200
    tools = listed.json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert names == ["dqa.mcp_ready"]
    assert "demis.search_schema" not in names


def test_mcp_ready_tool_no_side_effects(
    mcp_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def _boom(*_a: object, **_k: object) -> object:
        calls.append("demis")
        raise AssertionError("DEMIS must not be touched")

    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        _boom,
        raising=False,
    )

    response = _mcp_post(
        mcp_client,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "dqa.mcp_ready", "arguments": {}},
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "result" in payload
    # structured content / text content depending on SDK serialization
    raw = json.dumps(payload)
    assert "28-A" in raw
    assert "mcp-tester" in raw
    assert calls == []
    assert "password" not in raw.lower()
    assert "secret" not in raw.lower()


def test_unauthenticated_mcp_rejected(mcp_client: TestClient) -> None:
    response = mcp_client.post(
        "/mcp/",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "anon", "version": "0"},
            },
        },
    )
    assert response.status_code == 401
    detail = response.json()["detail"]
    assert detail["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED
    assert "password" not in json.dumps(detail).lower()


def test_forged_identity_header_rejected(mcp_client: TestClient) -> None:
    response = _mcp_post(
        mcp_client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "forge", "version": "0"},
            },
        },
        headers={"X-User-Id": "admin", "X-Roles": "administrator"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_INVALID


def test_forged_identity_tool_arguments_rejected(mcp_client: TestClient) -> None:
    response = _mcp_post(
        mcp_client,
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "dqa.mcp_ready",
                "arguments": {"user_id": "admin", "roles": ["administrator"]},
            },
        },
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_INVALID


def test_production_auth_disabled_fail_closed(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "disabled")
    monkeypatch.setenv("DQA_MCP_ENABLED", "true")
    _clear_caches()
    from app.main import create_app

    application = create_app(check_migrations_on_startup=False)
    with TestClient(application) as client:
        response = client.post(
            "/mcp/",
            headers=_MCP_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "prod", "version": "0"},
                },
            },
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    _clear_caches()


def test_dev_headers_not_available_in_production_mcp(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    monkeypatch.setenv("DQA_MCP_ENABLED", "true")
    _clear_caches()
    from app.main import create_app

    application = create_app(check_migrations_on_startup=False)
    with TestClient(application) as client:
        response = client.post(
            "/mcp/",
            headers=_MCP_HEADERS,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "prod", "version": "0"},
                },
            },
        )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == AuthErrorCode.PROVIDER_UNAVAILABLE
    _clear_caches()


def test_adapter_readiness_is_side_effect_free() -> None:
    from app.auth.models import AuthenticatedActor, Role

    actor = AuthenticatedActor(
        actor_id="a1",
        roles=frozenset({Role.VIEWER}),
        provider="dev_headers",
    )
    result = McpApplicationAdapter().readiness(actor)
    assert result["phase"] == "28-A"
    assert result["client"] == "MCP"
    assert result["actor_id"] == "a1"
