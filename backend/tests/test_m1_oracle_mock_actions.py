"""M1 Oracle Mock UI-action contracts: entirely in-memory, no DB/Oracle I/O.

Do NOT import/use root db_session or db_client fixtures: they truncate DB tables.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode, DemisProbeState
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
