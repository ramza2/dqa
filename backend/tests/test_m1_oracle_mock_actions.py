"""M1 Oracle Mock UI-action contracts: entirely in-memory, no DB/Oracle I/O.

Do NOT import/use root db_session or db_client fixtures: they truncate DB tables.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.adapters.demis.types import DemisAdapterDiagnostics
from app.core.config import Settings
from app.services import oracle_mock_actions as m


def settings(**override):
    data = {
        "APP_ENV": "development",
        "DQA_AUTH_PROVIDER": "dev_headers",
        "DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED": True,
    }
    data.update(override)
    return Settings(_env_file=None, **data)


def profile(**override):
    data = dict(
        id=17,
        name="DEMIS Oracle Mock - Development",
        source_name=m.MOCK_SOURCE,
        environment=m.MOCK_ENVIRONMENT,
        dbms_type=m.MOCK_DBMS,
        host=m.MOCK_HOST,
        port=m.MOCK_PORT,
        database_name=m.MOCK_SERVICE,
        username=m.MOCK_USERNAME,
        credential_secret_ref=m.MOCK_CREDENTIAL_REF,
        enabled=False,
        created_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
        updated_at=datetime(2026, 10, 23, tzinfo=timezone.utc),
    )
    data.update(override)
    return SimpleNamespace(**data)


@pytest.mark.parametrize("override", [
    {"APP_ENV": "production"},
    {"APP_ENV": "staging"},
    {"DQA_AUTH_PROVIDER": "disabled"},
    {"DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED": False},
])
def test_gate_denies_without_entering_repo_or_connecting(monkeypatch, override):
    assert not m.oracle_mock_actions_available(settings(**override))
    monkeypatch.setattr(m, "ConnectionProfileRepository",
                        lambda *_a: pytest.fail("must not reach DB"))
    with pytest.raises(m.OracleMockActionError, match="ORACLE_MOCK_ACTIONS_DISABLED"):
        m.test_oracle_mock_profile(object(), 17, settings(**override))
    with pytest.raises(m.OracleMockActionError):
        m.create_or_get_oracle_mock_profile(object(), settings(**override), actor="admin")


@pytest.mark.parametrize("change", [
    {"source_name": "demis_production"},
    {"environment": "production"},
    {"host": "demis.internal"},
    {"port": 1522},
    {"database_name": "OTHER"},
    {"dbms_type": "postgresql"},
    {"username": "SYS"},
    {"credential_secret_ref": "env:DEMIS_SECRET_REAL"},
])
def test_pinned_identity_is_all_fields_or_nothing(change):
    with pytest.raises(m.OracleMockActionError, match="ORACLE_MOCK_TARGET_MISMATCH"):
        m._check_mock_target(profile(**change))


def test_disabled_mock_live_probe_uses_ephemeral_enabled_snapshot(monkeypatch):
    p = profile()
    class Repo:
        def __init__(self, _session): pass
        def get_by_id_for_update(self, profile_id):
            assert profile_id == 17
            return p
    monkeypatch.setattr(m, "ConnectionProfileRepository", Repo)
    monkeypatch.setattr(m, "create_credential_resolver", lambda: object())
    def _snapshot(given):
        assert given is p and given.enabled is False
        class Snapshot:
            def model_copy(self, *, update):
                assert update == {"enabled": True}
                return SimpleNamespace(enabled=True)
        return Snapshot()
    import app.services.connection_profile as cp
    monkeypatch.setattr(cp, "_profile_snapshot", _snapshot)
    calls = []
    def factory(snapshot, *, credential_resolver):
        assert snapshot.enabled is True
        calls.append("factory")
        return SimpleNamespace(probe_readonly=lambda: DemisAdapterDiagnostics(
            configured=True, dbms_type="oracle",
            live_connection_tested=True, reachable=True, read_only=True,
            failure_category=None
        ))
    monkeypatch.setattr(m, "create_readonly_demis_adapter", factory)
    result = m.test_oracle_mock_profile(object(), 17, settings())
    assert result.status == "SUCCEEDED"
    assert result.read_only is True
    assert p.enabled is False
    assert calls == ["factory"]


def test_probe_failure_does_not_enable_profile(monkeypatch):
    p = profile()
    class Repo:
        def __init__(self, _session): pass
        def get_by_id_for_update(self, profile_id): return p
    monkeypatch.setattr(m, "ConnectionProfileRepository", Repo)
    monkeypatch.setattr(m, "_probe_mock_profile",
        lambda _p: SimpleNamespace(status="FAILED", live_connection_tested=True,
            reachable=True, read_only=False))
    monkeypatch.setattr(m, "enable_connection_profile",
        lambda *_a, **_kw: pytest.fail("must not enable on failed probe"))
    with pytest.raises(m.OracleMockActionError, match="ORACLE_MOCK_READONLY_PROBE_REQUIRED"):
        m.enable_oracle_mock_profile(object(), 17, settings(), actor="admin")
    assert p.enabled is False


def test_enable_requires_new_server_probe_not_previous_ui_result(monkeypatch):
    p = profile()
    class Repo:
        def __init__(self, _session): pass
        def get_by_id_for_update(self, profile_id):
            assert profile_id == 17
            return p
    monkeypatch.setattr(m, "ConnectionProfileRepository", Repo)
    calls = []
    def probe(given):
        assert given is p
        calls.append("probe")
        return SimpleNamespace(
            status="SUCCEEDED", live_connection_tested=True,
            reachable=True, read_only=True)
    monkeypatch.setattr(m, "_probe_mock_profile", probe)
    def enable(_session, _id, *, actor):
        assert actor == "admin"
        calls.append("enable")
        p.enabled = True
    monkeypatch.setattr(m, "enable_connection_profile", enable)
    monkeypatch.setattr(m, "get_connection_profile", lambda _s, _i: p)
    result = m.enable_oracle_mock_profile(object(), 17, settings(), actor="admin")
    assert result.enabled
    assert calls == ["probe", "enable"]


def test_mock_existing_profile_identity_checked_before_return(monkeypatch):
    p = profile(host="production.invalid")
    class Repo:
        def __init__(self, _session): pass
        def get_by_source_and_environment(self, src, env):
            assert (src, env) == (m.MOCK_SOURCE, m.MOCK_ENVIRONMENT)
            return p
    monkeypatch.setattr(m, "ConnectionProfileRepository", Repo)
    monkeypatch.setattr(m, "get_connection_profile", lambda *_a:
                        pytest.fail("invalid profile cannot be selected"))
    monkeypatch.setattr(m, "create_connection_profile", lambda *_a, **_kw:
                        pytest.fail("existing profile cannot be overwritten"))
    with pytest.raises(m.OracleMockActionError, match="ORACLE_MOCK_TARGET_MISMATCH"):
        m.create_or_get_oracle_mock_profile(object(), settings(), actor="admin")

def test_http_capability_and_restricted_routes_never_touch_oracle(client, monkeypatch):
    """Use TestClient with a fake DB dependency, never db_session / migrate."""
    from app.adapters.db.deps import get_db_session
    from app.core.config import get_settings
    from app.api.routes import connection_profiles as routes

    def no_db():
        yield object()

    client.app.dependency_overrides[get_db_session] = no_db
    client.app.dependency_overrides[get_settings] = lambda: settings()
    calls = []
    def register(_session, _settings, *, actor):
        calls.append(("register", actor))
        return profile(id=17)
    def probe(_session, ident, _settings):
        calls.append(("probe", ident))
        return SimpleNamespace(
            profile_id=ident, source_name=m.MOCK_SOURCE, environment=m.MOCK_ENVIRONMENT,
            status="SUCCEEDED", live_connection_tested=True,
            reachable=True, read_only=True, failure_category=None,
        )
    def enabled(_session, ident, _settings, *, actor):
        calls.append(("enable", ident))
        return profile(id=ident, enabled=True)
    monkeypatch.setattr(routes, "create_or_get_oracle_mock_profile", register)
    monkeypatch.setattr(routes, "test_oracle_mock_profile", probe)
    monkeypatch.setattr(routes, "enable_oracle_mock_profile", enabled)
    try:
        capability = client.get("/api/v1/connection-profiles/oracle-mock-capability")
        assert capability.status_code == 200
        assert capability.json() == {"enabled": True}

        denied = client.post(
            "/api/v1/connection-profiles/17/oracle-mock-test",
            headers={
                "X-DQA-Dev-Actor": "not-admin",
                "X-DQA-Dev-Roles": "viewer",
            },
        )
        assert denied.status_code == 403
        assert calls == []

        registered = client.post("/api/v1/connection-profiles/oracle-mock-profile")
        assert registered.status_code == 200
        assert registered.json()["source_name"] == m.MOCK_SOURCE
        tested = client.post("/api/v1/connection-profiles/17/oracle-mock-test")
        assert tested.status_code == 200
        assert tested.json()["read_only"] is True
        activated = client.post("/api/v1/connection-profiles/17/oracle-mock-enable")
        assert activated.status_code == 200
        assert activated.json()["enabled"] is True
        assert calls == [("register", "test-admin"), ("probe", 17), ("enable", 17)]
    finally:
        client.app.dependency_overrides.clear()


def test_http_mock_actions_default_off(client, monkeypatch):
    from app.adapters.db.deps import get_db_session
    from app.core.config import get_settings
    from app.api.routes import connection_profiles as routes

    def no_db():
        yield object()

    client.app.dependency_overrides[get_db_session] = no_db
    client.app.dependency_overrides[get_settings] = lambda: settings(
        DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED=False
    )
    monkeypatch.setattr(routes, "create_or_get_oracle_mock_profile", lambda *_a, **_kw:
                        pytest.fail("service must not be called after gate"))
    # Route gate is service-level; do not try to infer protection from UI.
    # In this test use actual service implementation and a repo fail trap.
    monkeypatch.setattr(routes, "create_or_get_oracle_mock_profile", m.create_or_get_oracle_mock_profile)
    monkeypatch.setattr(m, "ConnectionProfileRepository", lambda *_a:
                        pytest.fail("no DB on disabled action"))
    try:
        capability = client.get("/api/v1/connection-profiles/oracle-mock-capability")
        assert capability.json() == {"enabled": False}
        registered = client.post("/api/v1/connection-profiles/oracle-mock-profile")
        assert registered.status_code == 403
        assert registered.json()["detail"]["code"] == "ORACLE_MOCK_ACTIONS_DISABLED"
    finally:
        client.app.dependency_overrides.clear()
