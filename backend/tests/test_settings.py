"""Settings and configuration unit tests."""

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
    assert "super-secret" in settings.database_url
    assert "super-secret" not in settings.database_url_safe
    assert "***" in settings.database_url_safe
    assert settings.database_url_safe.startswith("postgresql+psycopg://dqa:***@db.example:5432/dqa")


def test_get_settings_reads_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DQA_DB_HOST", "localhost")
    monkeypatch.setenv("DQA_DB_PASSWORD", "dqa")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.app_env == "test"
        assert settings.dqa_db_host == "localhost"
        assert settings.dqa_db_password.get_secret_value() == "dqa"
    finally:
        get_settings.cache_clear()
