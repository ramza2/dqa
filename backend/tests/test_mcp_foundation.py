"""Phase 28-A: MCP server foundation (transport, auth, registry; no query tools)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.auth.errors import AuthErrorCode
from app.core.config import Settings, get_settings
from app.mcp.adapter import McpApplicationAdapter
from app.mcp.auth import (
    McpAuthMiddleware,
    McpBodyStreamError,
    McpBodyTooLargeError,
    read_body_bounded,
)
from app.mcp.ingress import (
    is_loopback_host_declaration,
    is_trusted_mcp_peer,
    should_mount_mcp,
)
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


def _asgi_mcp_post(
    application: Any,
    payload: dict[str, Any],
    *,
    client_host: str = "127.0.0.1",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    """POST /mcp/ through ASGI with an explicit peer host (TestClient uses testclient)."""
    body = json.dumps(payload).encode("utf-8")
    hdrs = {**_MCP_HEADERS, **(headers or {})}
    header_list = [
        (k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in hdrs.items()
    ]
    header_list.append((b"content-length", str(len(body)).encode("latin-1")))
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/mcp/",
        "raw_path": b"/mcp/",
        "root_path": "",
        "query_string": b"",
        "headers": header_list,
        "client": (client_host, 12345),
        "server": ("127.0.0.1", 8000),
        "scheme": "http",
    }

    async def _run() -> None:
        await application(scope, receive, send)

    asyncio.run(_run())
    start = next(m for m in sent if m["type"] == "http.response.start")
    chunks = b"".join(
        m.get("body", b"") for m in sent if m["type"] == "http.response.body"
    )
    parsed: dict[str, Any] = json.loads(chunks.decode()) if chunks else {}
    return int(start["status"]), parsed


def test_production_auth_disabled_fail_closed(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "disabled")
    monkeypatch.setenv("DQA_MCP_ENABLED", "true")
    monkeypatch.setenv("DQA_MCP_BIND_HOST", "127.0.0.1")
    _clear_caches()
    from app.main import create_app

    application = create_app(check_migrations_on_startup=False)
    # Use loopback peer: production rejects Starlette's "testclient" host at ingress.
    status, detail = _asgi_mcp_post(
        application,
        {
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
    assert status == 503
    assert detail["detail"]["code"] == AuthErrorCode.PROVIDER_NOT_CONFIGURED
    _clear_caches()


def test_dev_headers_not_available_in_production_mcp(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    monkeypatch.setenv("DQA_MCP_ENABLED", "true")
    monkeypatch.setenv("DQA_MCP_BIND_HOST", "127.0.0.1")
    _clear_caches()
    from app.main import create_app

    application = create_app(check_migrations_on_startup=False)
    status, detail = _asgi_mcp_post(
        application,
        {
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
    assert status == 503
    assert detail["detail"]["code"] == AuthErrorCode.PROVIDER_UNAVAILABLE
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


# --- Body bound / stream / ingress hardening ---------------------------------


def test_read_body_bounded_accepts_within_limit() -> None:
    chunks = [
        {"type": "http.request", "body": b"abc", "more_body": True},
        {"type": "http.request", "body": b"def", "more_body": False},
    ]

    async def receive() -> dict[str, Any]:
        return chunks.pop(0)

    body = asyncio.run(read_body_bounded(receive, max_bytes=16))
    assert body == b"abcdef"


def test_read_body_bounded_rejects_oversized() -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"x" * 8, "more_body": False}

    with pytest.raises(McpBodyTooLargeError):
        asyncio.run(read_body_bounded(receive, max_bytes=4))


def test_read_body_bounded_handles_disconnect() -> None:
    async def receive() -> dict[str, Any]:
        return {"type": "http.disconnect"}

    with pytest.raises(McpBodyStreamError, match="disconnected"):
        asyncio.run(read_body_bounded(receive, max_bytes=1024))


def test_read_body_bounded_rejects_malformed_stream_and_infinite_frames() -> None:
    async def bad_type() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    with pytest.raises(McpBodyStreamError, match="malformed"):
        asyncio.run(read_body_bounded(bad_type, max_bytes=16))

    async def endless_empty() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": True}

    with pytest.raises(McpBodyStreamError, match="malformed"):
        asyncio.run(read_body_bounded(endless_empty, max_bytes=4))


def test_loopback_host_declaration_and_mount_gate() -> None:
    assert is_loopback_host_declaration("127.0.0.1")
    assert is_loopback_host_declaration("::1")
    assert is_loopback_host_declaration("localhost")
    assert not is_loopback_host_declaration("0.0.0.0")
    assert not is_loopback_host_declaration("192.168.1.10")
    assert not is_loopback_host_declaration("")

    enabled = Settings(
        APP_ENV="test",
        DQA_MCP_ENABLED=True,
        DQA_MCP_BIND_HOST="127.0.0.1",
    )
    assert should_mount_mcp(enabled) is True

    public_decl = Settings(
        APP_ENV="test",
        DQA_MCP_ENABLED=True,
        DQA_MCP_BIND_HOST="0.0.0.0",
    )
    assert should_mount_mcp(public_decl) is False

    disabled = Settings(
        APP_ENV="test",
        DQA_MCP_ENABLED=False,
        DQA_MCP_BIND_HOST="127.0.0.1",
    )
    assert should_mount_mcp(disabled) is False


def test_trusted_mcp_peer_loopback_only() -> None:
    settings = Settings(APP_ENV="test", DQA_MCP_ENABLED=True)
    assert is_trusted_mcp_peer({"type": "http", "client": ("127.0.0.1", 9)}, settings)
    assert is_trusted_mcp_peer({"type": "http", "client": ("::1", 9)}, settings)
    assert is_trusted_mcp_peer({"type": "http", "client": ("testclient", 9)}, settings)
    assert not is_trusted_mcp_peer(
        {"type": "http", "client": ("203.0.113.50", 9)}, settings
    )
    prod = Settings(APP_ENV="production", DQA_MCP_ENABLED=True)
    assert not is_trusted_mcp_peer({"type": "http", "client": None}, prod)


def test_oversized_body_returns_413(
    mcp_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DQA_MCP_MAX_BODY_BYTES", "2048")
    _clear_caches()
    from app.main import create_app

    application = create_app(check_migrations_on_startup=False)
    with TestClient(application) as client:
        huge = "x" * 4096
        response = client.post(
            "/mcp/",
            headers=_MCP_HEADERS,
            content=huge.encode("utf-8"),
        )
        assert response.status_code == 413
        assert response.json()["detail"]["code"] == "MCP_BODY_TOO_LARGE"
    _clear_caches()


def test_content_length_oversize_returns_413_without_full_body(
    mcp_client: TestClient,
) -> None:
    """Content-Length above the limit is rejected before streaming the body."""

    async def _inner() -> None:
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            raise AssertionError("body must not be read when Content-Length is oversized")

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        settings = get_settings()

        async def passthrough(scope: Any, receive: Any, send: Any) -> None:
            raise AssertionError("downstream must not run")

        app = McpAuthMiddleware(
            passthrough, settings=settings, max_body_bytes=1024
        )
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", b"99999"),
                (b"accept", b"application/json"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
        }
        await app(scope, receive, send)
        start = next(m for m in sent if m["type"] == "http.response.start")
        assert start["status"] == 413

    asyncio.run(_inner())


def test_disconnect_during_body_returns_400(mcp_client: TestClient) -> None:
    async def _inner() -> None:
        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        settings = get_settings()

        async def passthrough(scope: Any, receive: Any, send: Any) -> None:
            raise AssertionError("downstream must not run")

        app = McpAuthMiddleware(
            passthrough, settings=settings, max_body_bytes=65536
        )
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [
                (b"content-type", b"application/json"),
                (b"accept", b"application/json"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
        }
        await app(scope, receive, send)
        start = next(m for m in sent if m["type"] == "http.response.start")
        assert start["status"] == 400
        body_msg = next(m for m in sent if m["type"] == "http.response.body")
        detail = json.loads(body_msg["body"].decode())
        assert detail["detail"]["code"] == "MCP_BODY_INCOMPLETE"

    asyncio.run(_inner())


def test_non_loopback_peer_ingress_denied(mcp_client: TestClient) -> None:
    async def _inner() -> None:
        from app.mcp.ingress import McpIngressMiddleware

        sent: list[dict[str, Any]] = []

        async def receive() -> dict[str, Any]:
            return {"type": "http.request", "body": b"{}", "more_body": False}

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        settings = get_settings()

        async def passthrough(scope: Any, receive: Any, send: Any) -> None:
            raise AssertionError("downstream must not run for untrusted peer")

        app = McpIngressMiddleware(passthrough, settings=settings)
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("203.0.113.9", 4444),
            "server": ("0.0.0.0", 8000),
            "scheme": "http",
        }
        await app(scope, receive, send)
        start = next(m for m in sent if m["type"] == "http.response.start")
        assert start["status"] == 403
        body_msg = next(m for m in sent if m["type"] == "http.response.body")
        detail = json.loads(body_msg["body"].decode())
        assert detail["detail"]["code"] == "MCP_INGRESS_DENIED"

    asyncio.run(_inner())


def test_non_loopback_bind_host_refuses_mcp_mount_web_apis_ok(
    monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setenv("DQA_MCP_ENABLED", "true")
    monkeypatch.setenv("DQA_MCP_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    monkeypatch.setenv("APP_ENV", "test")
    _clear_caches()
    from app.main import create_app

    application = create_app(check_migrations_on_startup=False)
    with TestClient(application) as client:
        mcp = client.post(
            "/mcp/",
            headers=_MCP_HEADERS,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        )
        assert mcp.status_code == 404
        health = client.get("/health")
        assert health.status_code == 200
    _clear_caches()


def test_initialize_list_and_tools_call_happy_path(mcp_client: TestClient) -> None:
    """Regression: initialize → tools/list → tools/call remain available."""
    init = _mcp_post(
        mcp_client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dqa-secure", "version": "0"},
            },
        },
    )
    assert init.status_code == 200
    listed = _mcp_post(
        mcp_client,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert listed.status_code == 200
    names = [t["name"] for t in listed.json()["result"]["tools"]]
    assert names == ["dqa.mcp_ready"]
    called = _mcp_post(
        mcp_client,
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "dqa.mcp_ready", "arguments": {}},
        },
    )
    assert called.status_code == 200
    assert "28-A" in json.dumps(called.json())
