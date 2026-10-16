"""P30-C: marker-verified test DB only. Never request db_session/db_client.

Root conftest.db_session performs TRUNCATE on whichever DB is configured.
This package deliberately avoids that fixture entirely. Each test verifies the
dedicated database identity BEFORE constructing its own SQLAlchemy Session.
"""
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings

_EXPECTED = {
    "APP_ENV": "test",
    "DQA_AUTH_PROVIDER": "dev_headers",
    "DQA_DB_HOST": "127.0.0.1",
    "DQA_DB_PORT": "55448",
    "DQA_DB_NAME": "dqa_p30c_disposable",
    "DQA_DB_USER": "dqa_p30c_user",
    "DQA_DB_PASSWORD": "p30c_synthetic_only",
    "DQA_P30C_ISOLATED_PG": "p30c-v1",
}
_MARKER = "DQA_P30C_DISPOSABLE_DB_V1"


@pytest.fixture()
def p30c_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[sessionmaker[Session]]:
    mismatches = [
        name for name, value in _EXPECTED.items()
        if os.environ.get(name) != value
    ]
    if mismatches:
        pytest.fail(
            "P30C_REFUSED: isolated DB configuration mismatch: "
            + ",".join(mismatches),
            pytrace=False,
        )

    settings = Settings(_env_file=None)
    if (
        settings.app_env, settings.dqa_auth_provider,
        settings.dqa_db_host, settings.dqa_db_port,
        settings.dqa_db_name, settings.dqa_db_user,
    ) != (
        "test", "dev_headers", "127.0.0.1", 55448,
        "dqa_p30c_disposable", "dqa_p30c_user",
    ):
        pytest.fail("P30C_REFUSED: unsafe DB connection settings", pytrace=False)

    engine = create_engine(
        settings.sqlalchemy_database_url,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT current_database(), current_user, "
                "(SELECT shobj_description(oid, 'pg_database') "
                "FROM pg_database WHERE datname = current_database())"
            )).one()
            if tuple(row) != (
                "dqa_p30c_disposable", "dqa_p30c_user", _MARKER
            ):
                pytest.fail("P30C_REFUSED: database identity marker missing", pytrace=False)
            for table in (
                "catalog_import_revisions", "catalog_active_revisions",
                "data_discovery_documents", "data_discovery_embeddings",
            ):
                if conn.scalar(text("SELECT to_regclass(:t)"), {"t": "public." + table}) is None:
                    pytest.fail("P30C_REFUSED: missing migration table", pytrace=False)
        # No implicit env inherited from developer's .env for embedding calls.
        monkeypatch.setenv("EMBEDDING_BASE_URL", "https://embedding.invalid/v1")
        monkeypatch.setenv("EMBEDDING_MODEL", "stub-bge-m3")
        monkeypatch.setenv("LLM_BASE_URL", "")
        monkeypatch.setenv("LLM_API_KEY", "")
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
