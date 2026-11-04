"""No live PostgreSQL/DEMIS: isolated in-memory tests for operator login."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.local_session import hash_password, utcnow, verify_password
from app.auth.models import Role
from app.models.base import Base
from app.models.local_auth import LocalSession, LocalUser


@pytest.fixture()
def local_auth(monkeypatch: pytest.MonkeyPatch):
    from app.adapters.db import session as db_sessions
    from app.core.config import get_settings
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "local_session")
    monkeypatch.setenv("DQA_LOCAL_AUTH_ORIGIN", "http://testserver")
    monkeypatch.setenv("DQA_LOCAL_AUTH_CSRF_KEY", "synthetic-tests-only-key-with-32-chars!")
    monkeypatch.setenv("DQA_LOCAL_AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("DQA_MCP_ENABLED", "false")
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine, tables=[LocalUser.__table__, LocalSession.__table__])
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(db_sessions, "get_session_factory", lambda database_url=None: factory)
    with factory.begin() as db:
        db.add_all([
            LocalUser(username="admin1", display_name="Administrator", roles=[Role.ADMINISTRATOR.value],
                      password_hash=hash_password("strong-synthetic-password"), is_active=True,
                      failed_login_count=0),
            LocalUser(username="viewer1", display_name="Viewer", roles=[Role.VIEWER.value],
                      password_hash=hash_password("strong-synthetic-password"), is_active=True,
                      failed_login_count=0),
        ])
    app = create_app(check_migrations_on_startup=False)
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()
    get_settings.cache_clear()


ORIGIN = {"Origin": "http://testserver"}


def login(client: TestClient, *, username: str = "admin1", password: str = "strong-synthetic-password"):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password}, headers=ORIGIN)


def test_password_hash_is_salted_and_malformed_input_fails() -> None:
    first = hash_password("strong-synthetic-password")
    second = hash_password("strong-synthetic-password")
    assert first != second
    assert "strong-synthetic-password" not in first
    assert verify_password("strong-synthetic-password", first)
    assert not verify_password("wrong-password", first)
    assert not verify_password("strong-synthetic-password", "invalid$hash")
    with pytest.raises(ValueError):
        hash_password("short")


def test_login_csrf_logout_and_header_spoof_rejected(local_auth) -> None:
    client, factory = local_auth
    assert client.get("/api/v1/auth/capabilities").json() == {
        "login_supported": True, "mode": "local_session",
    }
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 200
    identity = client.get("/api/v1/auth/me")
    assert identity.status_code == 200
    body = identity.json()
    assert body["actor_id"] == "admin1"
    assert body["roles"] == ["administrator"]
    assert body["provider"] == "local_session"
    assert len(body["csrf_token"]) == 64
    assert identity.headers["Cache-Control"] == "no-store"
    assert client.cookies.get("dqa_session")

    # Without CSRF token even an administrator cannot mutate settings.
    denied = client.post("/api/v1/auth/logout", headers=ORIGIN)
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "AUTH_CSRF_INVALID"
    forged = client.post("/api/v1/auth/logout", headers={
        **ORIGIN, "X-DQA-CSRF": body["csrf_token"],
        "X-DQA-Dev-Actor": "spoofed", "X-DQA-Dev-Roles": "administrator",
    })
    assert forged.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    with factory() as db:
        assert db.scalar(select(LocalSession)).revoked_at is not None


def test_origin_must_match_and_login_response_cookie_is_scoped(local_auth) -> None:
    client, _ = local_auth
    assert client.post("/api/v1/auth/login", json={
        "username": "admin1", "password": "strong-synthetic-password",
    }, headers={"Origin": "https://attacker.example"}).status_code == 403
    result = login(client)
    assert result.status_code == 200
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert "Path=/api/v1" in cookie
    csrf = result.json()["csrf_token"]
    assert client.post("/api/v1/auth/logout", headers={
        "Origin": "https://attacker.example", "X-DQA-CSRF": csrf,
    }).status_code == 403


def test_lockout_roles_expiration_and_disabled_user(local_auth) -> None:
    client, factory = local_auth
    for _ in range(5):
        assert login(client, username="viewer1", password="incorrect").status_code == 401
    assert login(client, username="viewer1").status_code == 401
    with factory.begin() as db:
        user = db.scalar(select(LocalUser).where(LocalUser.username == "viewer1"))
        assert user.failed_login_count == 5
        assert user.locked_until.replace(tzinfo=user.locked_until.tzinfo or utcnow().tzinfo) > utcnow()
        user.locked_until = utcnow() - timedelta(seconds=1)
    assert login(client, username="viewer1").status_code == 200
    identity = client.get("/api/v1/auth/me").json()
    assert identity["roles"] == ["viewer"]
    assert client.get("/api/v1/connection-profiles").status_code == 403
    with factory.begin() as db:
        session = db.scalar(select(LocalSession).order_by(LocalSession.id.desc()))
        session.expires_at = utcnow() - timedelta(seconds=1)
    assert client.get("/api/v1/auth/me").status_code == 401

    assert login(client, username="viewer1").status_code == 200
    with factory.begin() as db:
        user = db.scalar(select(LocalUser).where(LocalUser.username == "viewer1"))
        user.is_active = False
    assert client.get("/api/v1/auth/me").status_code == 401


def test_local_provider_fail_closed_without_secure_production_config(monkeypatch) -> None:
    from app.auth.errors import AuthError
    from app.auth.factory import create_identity_provider
    from app.core.config import Settings

    params = {
        "APP_ENV": "production", "DQA_AUTH_PROVIDER": "local_session",
        "DQA_LOCAL_AUTH_ORIGIN": "http://localhost:8080",
        "DQA_LOCAL_AUTH_CSRF_KEY": "synthetic-tests-only-key-with-32-chars!",
        "DQA_LOCAL_AUTH_COOKIE_SECURE": "false",
    }
    settings = Settings(**params)
    with pytest.raises(AuthError) as exc:
        create_identity_provider(settings)
    assert exc.value.code == "AUTH_PROVIDER_UNAVAILABLE"
    settings = Settings(**{**params, "DQA_LOCAL_AUTH_ORIGIN": "https://dqa.example", "DQA_LOCAL_AUTH_COOKIE_SECURE": True})
    assert create_identity_provider(settings).settings.app_env == "production"


def test_cli_provision_password_rotation_and_admin_protection(local_auth, monkeypatch) -> None:
    from app.cli import local_users
    client, factory = local_auth
    monkeypatch.setattr(local_users, "_password_prompt", lambda: hash_password("another-synthetic-password"))
    assert local_users.main(["create", "--username", "new-viewer", "--role", "viewer"]) == 0
    assert local_users.main(["create", "--username", "new-viewer", "--role", "viewer"]) == 2
    assert login(client, username="new-viewer", password="another-synthetic-password").status_code == 200
    assert local_users.main(["set-password", "--username", "new-viewer"]) == 0
    assert client.get("/api/v1/auth/me").status_code == 401
    assert local_users.main(["disable", "--username", "new-viewer"]) == 0
    with factory() as db:
        viewer = db.scalar(select(LocalUser).where(LocalUser.username == "new-viewer"))
        assert viewer.is_active is False
        assert db.scalar(select(LocalSession).where(LocalSession.user_id == viewer.id)).revoked_at is not None
    assert local_users.main(["disable", "--username", "admin1"]) == 2
