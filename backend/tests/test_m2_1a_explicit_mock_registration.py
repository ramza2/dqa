"""M2-1A: explicit Mock registration safety — no DB or Oracle I/O."""
from types import SimpleNamespace
import pytest

from app.core.config import Settings
from app.schemas.connection_profile import ConnectionProfileCreateRequest
from app.services import oracle_mock_actions as m


def settings(**changes):
    args = dict(APP_ENV="development", DQA_AUTH_PROVIDER="dev_headers",
                DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED=True)
    args.update(changes)
    return Settings(_env_file=None, **args)


def body(**changes):
    args = dict(name="Explicit development sample", source_name=m.MOCK_SOURCE,
                environment=m.MOCK_ENVIRONMENT, dbms_type=m.MOCK_DBMS,
                host=m.MOCK_HOST, port=m.MOCK_PORT, database_name=m.MOCK_SERVICE,
                username=m.MOCK_USERNAME)
    args.update(changes)
    return ConnectionProfileCreateRequest(**args)


def test_explicit_registration_injects_only_server_secret(monkeypatch):
    calls = []
    def create(_session, data, *, actor):
        calls.append((data, actor))
        return SimpleNamespace(id=71, enabled=False)
    monkeypatch.setattr(m, "create_connection_profile", create)
    result = m.register_explicit_oracle_mock_target(object(), settings(), body(), actor="admin")
    assert result.id == 71
    assert calls[0][0].credential_secret_ref == m.MOCK_CREDENTIAL_REF
    assert calls[0][1] == "admin"


@pytest.mark.parametrize("change", [
    {"host": "other.invalid"}, {"port": 1522},
    {"source_name": "demis_live"}, {"environment": "production"},
    {"dbms_type": "postgres"}, {"database_name": "OTHER"},
    {"username": "SYS"}, {"credential_secret_ref": "env:OTHER"},
])
def test_invalid_target_denied_before_db(monkeypatch, change):
    monkeypatch.setattr(m, "create_connection_profile",
                        lambda *_a, **_kw: pytest.fail("must not reach DB"))
    with pytest.raises(m.OracleMockActionError, match="ORACLE_MOCK_TARGET_MISMATCH"):
        m.register_explicit_oracle_mock_target(object(), settings(), body(**change), actor="admin")


@pytest.mark.parametrize("change", [
    {"APP_ENV": "production"}, {"DQA_AUTH_PROVIDER": "disabled"},
    {"DQA_DEV_ORACLE_MOCK_ACTIONS_ENABLED": False},
])
def test_disabled_environment_denied_before_db(monkeypatch, change):
    monkeypatch.setattr(m, "create_connection_profile",
                        lambda *_a, **_kw: pytest.fail("must not reach DB"))
    with pytest.raises(m.OracleMockActionError, match="ORACLE_MOCK_ACTIONS_DISABLED"):
        m.register_explicit_oracle_mock_target(object(), settings(**change), body(), actor="admin")


def test_duplicate_profile_conflicts_without_implicit_selection(monkeypatch):
    from app.adapters.connection_profile.errors import (
        ConnectionProfileError, ConnectionProfileErrorCode,
    )
    def duplicate(*_args, **_kwargs):
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.DUPLICATE_SOURCE_ENVIRONMENT,
            "already registered",
        )
    monkeypatch.setattr(m, "create_connection_profile", duplicate)
    with pytest.raises(ConnectionProfileError) as exc:
        m.register_explicit_oracle_mock_target(
            object(), settings(), body(), actor="admin",
        )
    assert exc.value.code == ConnectionProfileErrorCode.DUPLICATE_SOURCE_ENVIRONMENT


def test_http_registration_admin_only_no_db_or_live_probe(client, monkeypatch):
    from datetime import datetime, timezone
    from app.adapters.db.deps import get_db_session
    from app.core.config import get_settings
    from app.api.routes import connection_profiles as routes

    def no_db():
        yield object()

    client.app.dependency_overrides[get_db_session] = no_db
    client.app.dependency_overrides[get_settings] = lambda: settings()
    calls = []
    def register(_session, _settings, request, *, actor):
        calls.append(actor)
        now = datetime(2026, 10, 27, tzinfo=timezone.utc)
        return {
            **request.model_dump(),
            "id": 71,
            "enabled": False,
            "credential_secret_ref": m.MOCK_CREDENTIAL_REF,
            "created_by": actor,
            "updated_by": actor,
            "created_at": now,
            "updated_at": now,
        }

    monkeypatch.setattr(routes, "register_explicit_oracle_mock_target", register)
    path = "/api/v1/connection-profiles/oracle-mock-register"
    payload = body().model_dump(exclude_none=True)
    try:
        denied = client.post(path, json=payload, headers={
            "X-DQA-Dev-Actor": "viewer",
            "X-DQA-Dev-Roles": "viewer",
        })
        assert denied.status_code == 403
        assert not calls
        result = client.post(path, json=payload)
        assert result.status_code == 201
        assert result.json()["id"] == 71
        assert result.json()["enabled"] is False
        assert result.json()["source_name"] == m.MOCK_SOURCE
        assert calls == ["test-admin"]
    finally:
        client.app.dependency_overrides.clear()
