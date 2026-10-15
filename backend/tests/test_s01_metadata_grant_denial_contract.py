"""S-01-B: offline Oracle metadata dictionary and grant-denial safety contract.

This is NOT a real DBA privilege test, issuer/identity proof or preflight approval.
Never connect to DEMIS or an Oracle instance. All connections are synthetic.
"""
from __future__ import annotations

import re

import pytest
from sqlalchemy import create_engine as sqlalchemy_create_engine

from app.adapters.schema_inspector.oracle import OracleSchemaInspector
from app.core.config import get_settings
from tests.test_schema_inspector_admin import _configure
from tests.test_schema_inspector_oracle import FakeConnection

URL = "/api/v1/schema-inspector/inspect"

# Exact SELECT dictionary dependencies of the existing Oracle Inspector.
# A DBA still must approve each view's effective metadata visibility and grants.
ALLOWED_DICTIONARY_VIEWS = frozenset({
    "ALL_TABLES",
    "ALL_TAB_COMMENTS",
    "ALL_TAB_COLUMNS",
    "ALL_COL_COMMENTS",
    "ALL_CONSTRAINTS",
    "ALL_CONS_COLUMNS",
    "ALL_INDEXES",
    "ALL_IND_COLUMNS",
})
DENIED_QUERY_PHASES = (
    "FROM ALL_TABLES T",
    "FROM ALL_TAB_COLUMNS TC",
    "FROM ALL_CONSTRAINTS C",
    "FROM ALL_INDEXES I",
)


def _dictionary_refs(sql: str) -> set[str]:
    return set(re.findall(r"\b(?:FROM|JOIN)\s+(ALL_[A-Z_]+)\b", sql.upper()))


def test_metadata_query_allowlist_matches_exact_runtime_dictionary_references():
    engine = FakeConnection()
    inspector = OracleSchemaInspector(engine, "SYNTHETIC_PDB")

    snapshot = inspector.inspect("DEMIS_OWNER")
    assert snapshot.schema_name == "DEMIS_OWNER"
    assert engine.readonly_starts == 1
    assert len(engine.calls) == 6

    referenced = set()
    for statement, params in engine.calls:
        assert statement.startswith("SELECT ")
        assert params == {"schema": "DEMIS_OWNER"}
        assert ":SCHEMA" in statement
        referenced.update(_dictionary_refs(statement))
    assert referenced == ALLOWED_DICTIONARY_VIEWS
    assert not engine.connected

    # Schema enumeration is also dictionary-only, with bound system exclusions.
    listed = inspector.list_schemas()
    assert "DEMIS_OWNER" in listed
    assert engine.readonly_starts == 2
    sql, params = engine.calls[-1]
    assert _dictionary_refs(sql) == {"ALL_TABLES"}
    assert "DEMIS_OWNER" not in params.values()
    assert params
    assert not engine.connected


class PrivilegeDeniedEngine(FakeConnection):
    """Synthetic role denied at an Oracle read-only or dictionary operation."""

    def __init__(self, blocked_at: str):
        super().__init__()
        self.blocked_at = blocked_at
        self.denials = 0

    def exec_driver_sql(self, sql):
        if self.blocked_at == "READ_ONLY_TX":
            self.denials += 1
            raise PermissionError("ORA-01031: synthetic privilege denied")
        return super().exec_driver_sql(sql)

    def execute(self, statement, parameters):
        normalized = " ".join(str(statement).split()).upper()
        if self.blocked_at in normalized:
            assert self._readonly, "no dictionary SELECT before READ ONLY"
            self.denials += 1
            raise PermissionError("ORA-01031: synthetic privilege denied")
        return super().execute(statement, parameters)


@pytest.mark.parametrize("blocked_at", ("READ_ONLY_TX", *DENIED_QUERY_PHASES))
def test_dictionary_denial_aborts_before_snapshot_and_closes_connection(blocked_at):
    engine = PrivilegeDeniedEngine(blocked_at)
    with pytest.raises(PermissionError, match="ORA-01031"):
        OracleSchemaInspector(engine, "SYNTHETIC_PDB").inspect("DEMIS_OWNER")
    assert engine.denials == 1
    assert not engine.connected
    if blocked_at == "READ_ONLY_TX":
        assert engine.calls == []
        assert engine.readonly_starts == 0
    else:
        assert engine.readonly_starts == 1
        # No later dictionary access should be attempted after the denied stage.
        assert not any(blocked_at in sql for sql, _ in engine.calls)


def test_synthetic_privilege_denial_is_sanitized_in_http_result(client, monkeypatch):
    _configure(monkeypatch)
    get_settings.cache_clear()
    from app.services import schema_inspection as service

    # SQLAlchemy engine is an inert in-memory SQLite object: no connection to
    # Oracle. Inspector is overridden to emulate Oracle grant denial.
    monkeypatch.setattr(
        service, "create_engine",
        lambda *_args, **_kwargs: sqlalchemy_create_engine("sqlite+pysqlite:///:memory:"),
    )

    class DeniedInspector:
        def __init__(self, *_args):
            pass

        def inspect(self, _schema):
            raise PermissionError(
                "ORA-01031: synthetic denied, sensitive-db-host sensitive-password"
            )

    monkeypatch.setattr(service, "OracleSchemaInspector", DeniedInspector)

    response = client.post(URL, json={})
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert detail["code"] == "INSPECTOR_METADATA_FAILED"
    assert "ORA-01031" not in response.text
    assert "sensitive-db-host" not in response.text
    assert "sensitive-password" not in response.text
    assert "READY" not in response.text
    assert "VERIFIED" not in response.text


@pytest.mark.parametrize("role", ("viewer", "query_operator", "auditor"))
def test_non_admin_cannot_trigger_dictionary_access_before_auth(
    unauth_client, monkeypatch, role
):
    _configure(monkeypatch)
    get_settings.cache_clear()
    from app.api.routes import schema_inspector as api

    def forbidden(*_args, **_kwargs):
        pytest.fail("unauthorized identity must never trigger inspection")

    monkeypatch.setattr(api, "inspect_configured_schema", forbidden)
    response = unauth_client.post(
        URL, json={},
        headers={"X-DQA-Dev-Actor": "synthetic", "X-DQA-Dev-Roles": role},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "AUTHORIZATION_DENIED"
