"""Phase 28-B: Discovery MCP tools (demis.search_schema / demis.describe_resource)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.errors import AuthError, AuthErrorCode
from app.auth.models import AuthenticatedActor, Permission, Role
from app.core.config import get_settings
from app.mcp.adapter import McpApplicationAdapter
from app.mcp.registry import build_foundation_registry
from app.models.catalog_import import CatalogImportRevision
from app.services.catalog_active import activate_catalog_revision
from app.services.data_discovery_document import rebuild_for_revision

pytestmark = pytest.mark.integration

SOURCE_A = "oracle_demis_mock"
SOURCE_B = "oracle_demis_other"
FINGERPRINT_A = "fp-mcp-discovery-a"
FINGERPRINT_B = "fp-mcp-discovery-b"

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "X-DQA-Dev-Actor": "mcp-viewer",
    "X-DQA-Dev-Roles": "viewer",
}


def _clear_caches() -> None:
    from app.adapters.db.session import get_engine, get_session_factory

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {
        "X-DQA-Dev-Actor": actor,
        "X-DQA-Dev-Roles": roles,
    }


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
def mcp_db_client(mcp_env: dict[str, str], db_session: Session) -> TestClient:
    """MCP-enabled TestClient sharing the Alembic-migrated test database."""
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


def _tool_call(
    client: TestClient,
    name: str,
    arguments: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    call_id: int = 10,
) -> Any:
    return _mcp_post(
        client,
        {
            "jsonrpc": "2.0",
            "id": call_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        headers=headers,
    )


def _catalog_docs() -> dict[str, Any]:
    tables = [
        {
            "table_key": "DEMIS_OWNER.TB_LAB_RESULT",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_LAB_RESULT",
            "table_comment": "laboratory blood glucose and liver function panels",
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_ADM_HIST",
            "table_comment": "patient admission history",
        },
    ]
    columns = [
        {
            "table_key": "DEMIS_OWNER.TB_LAB_RESULT",
            "column_name": "GLUCOSE",
            "data_type": "NUMBER",
            "column_comment": "blood glucose value",
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "column_name": "ADM_ID",
            "data_type": "NUMBER",
            "primary_key": True,
            "column_comment": "admission id",
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "column_name": "LAB_ID",
            "data_type": "NUMBER",
            "column_comment": "fk to lab",
        },
    ]
    relations = [
        {
            "constraint_name": "FK_ADM_LAB",
            "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "target_table_key": "DEMIS_OWNER.TB_LAB_RESULT",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "LAB_ID",
                    "target_column": "GLUCOSE",
                }
            ],
        }
    ]
    indexes = [
        {
            "index_name": "IX_ADM_ID",
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "unique": True,
            "columns": ["ADM_ID"],
        }
    ]
    return {
        "tables": tables,
        "columns": columns,
        "relations": relations,
        "indexes": indexes,
        "categories": [],
        "assignments": [],
    }


def _make_revision(
    session: Session,
    *,
    source_name: str,
    fingerprint: str,
    archive_sha256: str,
) -> CatalogImportRevision:
    docs = _catalog_docs()
    revision = CatalogImportRevision(
        source_name=source_name,
        db_type="oracle",
        database_name="FREEPDB1",
        default_schema="DEMIS_OWNER",
        package_format="demis-catalog-package",
        package_version="2.0",
        package_readiness="READY",
        schema_fingerprint=fingerprint,
        archive_sha256=archive_sha256,
        manifest_sha256="2" * 64,
        generated_at=datetime(2026, 10, 8, tzinfo=UTC),
        validation_status="VALID",
        table_count=len(docs["tables"]),
        column_count=len(docs["columns"]),
        relation_count=len(docs["relations"]),
        index_count=len(docs["indexes"]),
        category_count=0,
        category_assignment_count=0,
        managed_file_count=1,
        manifest_json={},
        database_json={},
        tables_json={"tables": docs["tables"]},
        columns_json={"columns": docs["columns"]},
        relations_json={"relations": docs["relations"]},
        indexes_json={"indexes": docs["indexes"]},
        categories_json={
            "categories": docs["categories"],
            "table_assignments": docs["assignments"],
        },
        erd_json={},
        latest_run_json={},
        schema_snapshot_json={},
        preflight_json={},
        latest_diff_json={},
        managed_file_digests_json={},
    )
    session.add(revision)
    session.flush()
    session.refresh(revision)
    return revision


def _prepare_active(
    session: Session,
    *,
    source_name: str = SOURCE_A,
    fingerprint: str = FINGERPRINT_A,
    archive_sha256: str = "1" * 64,
    rebuild: bool = True,
) -> CatalogImportRevision:
    rev = _make_revision(
        session,
        source_name=source_name,
        fingerprint=fingerprint,
        archive_sha256=archive_sha256,
    )
    activate_catalog_revision(session, rev.id)
    if rebuild:
        rebuild_for_revision(session, rev.id)
    session.commit()
    return rev


def _assert_no_sensitive_leak(payload: object) -> None:
    text = str(payload).lower()
    forbidden = (
        "api_key",
        "bearer ",
        "password",
        "secret",
        "postgresql://",
        "x-api-key",
        "select ",
        "insert ",
        "delete ",
    )
    for token in forbidden:
        assert token not in text, f"sensitive token leaked: {token}"


def _extract_tool_payload(response_json: dict[str, Any]) -> dict[str, Any]:
    """Normalize FastMCP tools/call JSON into a dict payload."""
    result = response_json.get("result")
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip().startswith("{"):
                    return json.loads(text)
    if "error" in response_json:
        return response_json
    raise AssertionError(f"unexpected tools/call payload: {response_json}")


def _tool_is_error(response_json: dict[str, Any]) -> bool:
    result = response_json.get("result")
    if isinstance(result, dict) and result.get("isError") is True:
        return True
    return False


def test_registry_discovery_permissions() -> None:
    registry = build_foundation_registry()
    search = registry.get("demis.search_schema")
    describe = registry.get("demis.describe_resource")
    assert search is not None and search.permission == Permission.CATALOG_READ
    assert describe is not None and describe.permission == Permission.CATALOG_READ


def test_initialize_list_and_discovery_calls(
    mcp_db_client: TestClient, db_session: Session
) -> None:
    rev = _prepare_active(db_session)

    init = _mcp_post(
        mcp_db_client,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "dqa-discovery", "version": "0"},
            },
        },
    )
    assert init.status_code == 200
    assert init.json()["result"]["serverInfo"]["name"] == "dqa-mcp"

    listed = _mcp_post(
        mcp_db_client,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    assert listed.status_code == 200
    names = sorted(t["name"] for t in listed.json()["result"]["tools"])
    assert names == [
        "demis.describe_resource",
        "demis.search_schema",
        "dqa.mcp_ready",
    ]

    search = _tool_call(
        mcp_db_client,
        "demis.search_schema",
        {
            "source_name": rev.source_name,
            "query": "glucose",
            "mode": "keyword",
            "top_k": 5,
        },
    )
    assert search.status_code == 200
    search_body = search.json()
    assert not _tool_is_error(search_body)
    search_payload = _extract_tool_payload(search_body)
    assert search_payload["source_name"] == rev.source_name
    assert search_payload["catalog_revision_id"] == rev.id
    assert search_payload["schema_fingerprint"] == rev.schema_fingerprint
    assert search_payload["mode"] == "keyword"
    assert isinstance(search_payload["results"], list)
    assert len(search_payload["results"]) >= 1
    _assert_no_sensitive_leak(search_payload)

    described = _tool_call(
        mcp_db_client,
        "demis.describe_resource",
        {
            "source_name": rev.source_name,
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_ADM_HIST",
        },
        call_id=11,
    )
    assert described.status_code == 200
    desc_body = described.json()
    assert not _tool_is_error(desc_body)
    desc = _extract_tool_payload(desc_body)
    assert desc["source_name"] == rev.source_name
    assert desc["revision_id"] == rev.id
    assert desc["schema_fingerprint"] == rev.schema_fingerprint
    assert desc["table"]["name"] == "TB_ADM_HIST"
    assert any(c["name"] == "ADM_ID" and c.get("is_primary_key") for c in desc["columns"])
    assert any(c["name"] == "ADM_ID" for c in desc["primary_key_columns"])
    assert any(r.get("referenced_table_name") == "TB_LAB_RESULT" for r in desc["relations"])
    assert "selectable_fields" not in desc
    assert "filterable_fields" not in desc
    assert "capabilities" not in desc
    assert "logical" not in json.dumps(desc).lower()
    _assert_no_sensitive_leak(desc)


def test_catalog_read_denied_at_middleware(
    mcp_db_client: TestClient, db_session: Session
) -> None:
    rev = _prepare_active(db_session)
    denied = _tool_call(
        mcp_db_client,
        "demis.search_schema",
        {"source_name": rev.source_name, "query": "glucose", "mode": "keyword"},
        headers=_headers("no-perms", ""),
    )
    assert denied.status_code == 403
    detail = denied.json()["detail"]
    assert detail["code"] == AuthErrorCode.AUTHORIZATION_DENIED
    _assert_no_sensitive_leak(denied.json())

    denied_describe = _tool_call(
        mcp_db_client,
        "demis.describe_resource",
        {
            "source_name": rev.source_name,
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_LAB_RESULT",
        },
        headers=_headers("no-perms", ""),
        call_id=12,
    )
    assert denied_describe.status_code == 403
    assert (
        denied_describe.json()["detail"]["code"] == AuthErrorCode.AUTHORIZATION_DENIED
    )


def test_adapter_enforces_catalog_read_boundary(db_session: Session) -> None:
    rev = _prepare_active(db_session)
    actor = AuthenticatedActor(
        actor_id="noperm",
        roles=frozenset(),
        provider="dev_headers",
    )
    adapter = McpApplicationAdapter()
    with pytest.raises(AuthError) as exc_info:
        adapter.search_schema(
            actor,
            source_name=rev.source_name,
            query="glucose",
            mode="keyword",
            session=db_session,
        )
    assert exc_info.value.code == AuthErrorCode.AUTHORIZATION_DENIED

    with pytest.raises(AuthError) as exc_info2:
        adapter.describe_resource(
            actor,
            source_name=rev.source_name,
            schema_name="DEMIS_OWNER",
            table_name="TB_LAB_RESULT",
            session=db_session,
        )
    assert exc_info2.value.code == AuthErrorCode.AUTHORIZATION_DENIED


def test_unknown_source_and_unknown_table(
    mcp_db_client: TestClient, db_session: Session
) -> None:
    rev = _prepare_active(db_session)

    missing_source = _tool_call(
        mcp_db_client,
        "demis.search_schema",
        {"source_name": "no_such_source", "query": "glucose", "mode": "keyword"},
    )
    assert missing_source.status_code == 200
    body = missing_source.json()
    assert _tool_is_error(body)
    payload = json.dumps(body)
    assert "CATALOG_ACTIVE_REVISION_NOT_FOUND" in payload
    _assert_no_sensitive_leak(body)

    missing_table = _tool_call(
        mcp_db_client,
        "demis.describe_resource",
        {
            "source_name": rev.source_name,
            "schema_name": "DEMIS_OWNER",
            "table_name": "NO_SUCH_TABLE",
        },
        call_id=13,
    )
    assert missing_table.status_code == 200
    table_body = missing_table.json()
    assert _tool_is_error(table_body)
    assert "CATALOG_TABLE_NOT_FOUND" in json.dumps(table_body)
    _assert_no_sensitive_leak(table_body)


def test_active_revision_fingerprint_and_source_isolation(
    mcp_db_client: TestClient, db_session: Session
) -> None:
    rev_a = _prepare_active(
        db_session,
        source_name=SOURCE_A,
        fingerprint=FINGERPRINT_A,
        archive_sha256="a" * 64,
    )
    rev_b = _prepare_active(
        db_session,
        source_name=SOURCE_B,
        fingerprint=FINGERPRINT_B,
        archive_sha256="b" * 64,
    )

    search_a = _tool_call(
        mcp_db_client,
        "demis.search_schema",
        {"source_name": SOURCE_A, "query": "TB_LAB_RESULT", "mode": "keyword"},
    )
    payload_a = _extract_tool_payload(search_a.json())
    assert payload_a["catalog_revision_id"] == rev_a.id
    assert payload_a["schema_fingerprint"] == FINGERPRINT_A
    assert payload_a["source_name"] == SOURCE_A

    search_b = _tool_call(
        mcp_db_client,
        "demis.search_schema",
        {"source_name": SOURCE_B, "query": "TB_LAB_RESULT", "mode": "keyword"},
        call_id=14,
    )
    payload_b = _extract_tool_payload(search_b.json())
    assert payload_b["catalog_revision_id"] == rev_b.id
    assert payload_b["schema_fingerprint"] == FINGERPRINT_B
    assert payload_b["source_name"] == SOURCE_B
    assert payload_a["catalog_revision_id"] != payload_b["catalog_revision_id"]

    desc = _tool_call(
        mcp_db_client,
        "demis.describe_resource",
        {
            "source_name": SOURCE_B,
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_LAB_RESULT",
        },
        call_id=15,
    )
    desc_payload = _extract_tool_payload(desc.json())
    assert desc_payload["revision_id"] == rev_b.id
    assert desc_payload["schema_fingerprint"] == FINGERPRINT_B


def test_missing_discovery_index_and_embedding_handled_safely(
    mcp_db_client: TestClient, db_session: Session
) -> None:
    # Active Catalog without discovery documents.
    rev = _prepare_active(db_session, rebuild=False)

    no_index = _tool_call(
        mcp_db_client,
        "demis.search_schema",
        {"source_name": rev.source_name, "query": "glucose", "mode": "keyword"},
    )
    assert no_index.status_code == 200
    assert _tool_is_error(no_index.json())
    assert "DISCOVERY_INDEX_NOT_READY" in json.dumps(no_index.json())
    _assert_no_sensitive_leak(no_index.json())

    # Semantic without embedding config → sanitized EMBEDDING_NOT_CONFIGURED.
    _prepare_active(
        db_session,
        source_name="oracle_demis_embed",
        fingerprint="fp-mcp-embed",
        archive_sha256="c" * 64,
        rebuild=True,
    )
    no_embed = _tool_call(
        mcp_db_client,
        "demis.search_schema",
        {
            "source_name": "oracle_demis_embed",
            "query": "glucose",
            "mode": "semantic",
        },
        call_id=16,
    )
    assert no_embed.status_code == 200
    assert _tool_is_error(no_embed.json())
    assert "EMBEDDING_NOT_CONFIGURED" in json.dumps(no_embed.json())
    _assert_no_sensitive_leak(no_embed.json())


def test_discovery_tools_never_touch_demis_or_query_execution(
    mcp_db_client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rev = _prepare_active(db_session)
    calls: list[str] = []

    def _boom_demis(*_a: object, **_k: object) -> object:
        calls.append("demis")
        raise AssertionError("DEMIS adapter must not be used")

    def _boom_exec(*_a: object, **_k: object) -> object:
        calls.append("query_execution")
        raise AssertionError("query execution must not be used")

    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        _boom_demis,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.query_execution.execute_approved_template",
        _boom_exec,
        raising=False,
    )

    search = _tool_call(
        mcp_db_client,
        "demis.search_schema",
        {"source_name": rev.source_name, "query": "glucose", "mode": "keyword"},
    )
    assert search.status_code == 200
    assert not _tool_is_error(search.json())

    described = _tool_call(
        mcp_db_client,
        "demis.describe_resource",
        {
            "source_name": rev.source_name,
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_LAB_RESULT",
        },
        call_id=17,
    )
    assert described.status_code == 200
    assert not _tool_is_error(described.json())
    assert calls == []


def test_mcp_auth_ingress_regression_still_holds(mcp_db_client: TestClient) -> None:
    """Existing auth/ingress behaviors remain after Discovery tool registration."""
    unauth = mcp_db_client.post(
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
    assert unauth.status_code == 401
    assert unauth.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_REQUIRED

    forged = _mcp_post(
        mcp_db_client,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "forge", "version": "0"},
            },
        },
        headers={"X-User-Id": "admin"},
    )
    assert forged.status_code == 401
    assert forged.json()["detail"]["code"] == AuthErrorCode.AUTHENTICATION_INVALID

    health = mcp_db_client.get("/health")
    assert health.status_code == 200
