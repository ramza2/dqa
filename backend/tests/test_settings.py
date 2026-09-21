"""Settings and configuration unit tests."""

from urllib.parse import unquote

from app.core.config import Settings, get_settings


def test_settings_build_safe_database_url() -> None:
    settings = Settings(
        APP_ENV="test",
        APP_NAME="DEMIS Query Assistant",
        DQA_DB_HOST="db.example",
        DQA_DB_PORT=5432,
        DQA_DB_NAME="dqa",
        DQA_DB_USER="dqa",
        DQA_DB_PASSWORD="super-secret",
    )
    assert settings.sqlalchemy_database_url.password == "super-secret"
    assert "super-secret" in settings.database_url
    assert "super-secret" not in settings.database_url_safe
    assert settings.database_url_safe.startswith("postgresql+psycopg://dqa:***@db.example:5432/dqa")


def test_settings_database_url_encodes_special_password_characters() -> None:
    special_password = "p@ss:w/ord#1"
    settings = Settings(
        APP_ENV="test",
        DQA_DB_HOST="db.example",
        DQA_DB_PORT=5432,
        DQA_DB_NAME="dqa",
        DQA_DB_USER="dqa_user",
        DQA_DB_PASSWORD=special_password,
    )

    url = settings.sqlalchemy_database_url
    assert url.password == special_password
    assert url.username == "dqa_user"
    assert url.host == "db.example"
    assert url.database == "dqa"

    rendered = settings.database_url
    # Password must be percent-encoded in the rendered string, not raw-concatenated.
    assert special_password not in rendered
    assert "%40" in rendered  # @
    assert "%3A" in rendered or "%3a" in rendered  # :
    assert "%2F" in rendered or "%2f" in rendered  # /
    assert "%23" in rendered  # #
    assert unquote(rendered.split("@", 1)[0].rsplit(":", 1)[-1]) == special_password

    safe = settings.database_url_safe
    assert special_password not in safe
    assert "***" in safe
    assert "p@ss" not in safe
    assert safe.startswith("postgresql+psycopg://dqa_user:***@db.example:5432/dqa")


def test_get_settings_reads_environment(monkeypatch, test_settings_env) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DQA_DB_HOST", "localhost")
    monkeypatch.setenv("DQA_DB_PASSWORD", "env-secret")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.app_env == "test"
        assert settings.dqa_db_host == "localhost"
        assert settings.dqa_db_password.get_secret_value() == "env-secret"
    finally:
        get_settings.cache_clear()
