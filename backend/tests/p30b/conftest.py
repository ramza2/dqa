"""P30-B safety fixture: override root test_settings_env for disposable DB ONLY.

Root db_session fixture performs TRUNCATE ... CASCADE. This fixture must finish
its target/marker checks BEFORE any db_session can be constructed. Do not
extend this fixture to other test directories.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from app.core.config import Settings

EXPECTED = {
    "APP_ENV": "test",
    "DQA_AUTH_PROVIDER": "dev_headers",
    "DQA_DB_HOST": "127.0.0.1",
    "DQA_DB_PORT": "55447",
    "DQA_DB_NAME": "dqa_p30b_disposable",
    "DQA_DB_USER": "dqa_p30b_user",
    "DQA_DB_PASSWORD": "p30b_synthetic_only",
    "DQA_P30B_ISOLATED_PG": "p30b-v1",
}
MARKER = "DQA_P30B_DISPOSABLE_DB_V1"


@pytest.fixture()
def test_settings_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Recheck safety on EVERY test; never silently redirect to developer DB."""
    mismatches = [
        name for name, expected in EXPECTED.items()
        if os.environ.get(name) != expected
    ]
    if mismatches:
        pytest.fail(
            "P30B_REFUSED: mandatory isolated DB variables not set: "
            + ",".join(mismatches),
            pytrace=False,
        )

    # Read-only verification, before allowing parent conftest.db_session to
    # migrate/truncate any tables.
    cfg = Settings(_env_file=None)
    assert (
        cfg.app_env, cfg.dqa_auth_provider, cfg.dqa_db_host, cfg.dqa_db_port,
        cfg.dqa_db_name, cfg.dqa_db_user,
    ) == (
        "test", "dev_headers", "127.0.0.1", 55447,
        "dqa_p30b_disposable", "dqa_p30b_user",
    ), "P30B_REFUSED: unsafe DB target"

    engine = create_engine(
        cfg.sqlalchemy_database_url,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT current_database(), current_user, "
                "(SELECT shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = current_database())"
            )).one()
            if tuple(row) != ("dqa_p30b_disposable", "dqa_p30b_user", MARKER):
                pytest.fail("P30B_REFUSED: database identity marker mismatch", pytrace=False)
    finally:
        engine.dispose()

    # These override inherited service/LLM settings, not the DB identities.
    overrides = {
        "DQA_MCP_ENABLED": "true",
        "DQA_MCP_MOUNT_PATH": "/mcp",
        "DQA_MCP_BIND_HOST": "127.0.0.1",
        "DQA_MCP_QUERY_EXECUTION_ENABLED": "true",
        "DQA_MCP_EXECUTION_TOKEN_KEY": (
            "cDMwYi1pbnRlZ3JhdGlvbi10ZXN0LWtleS0zMmJ5dGU="  # fixed 32-byte test-only key
        ),
        "DQA_MCP_EXECUTION_TOKEN_TTL_SECONDS": "300",
        "DQA_SCHEMA_INSPECTOR_ENABLED": "false",
        "DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED": "false",
        "LLM_BASE_URL": "",
        "LLM_API_KEY": "",
        "EMBEDDING_BASE_URL": "",
        "EMBEDDING_API_KEY": "",
    }
    # Token crypto requires exactly 32 test-key bytes; the literal above is
    # only a deliberately non-production base64 fixed fixture.
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    return {**EXPECTED, **overrides}
