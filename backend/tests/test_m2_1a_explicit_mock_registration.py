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
