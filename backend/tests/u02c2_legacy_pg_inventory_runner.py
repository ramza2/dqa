"""U-02-C-2 standalone runner: disposable Legacy PG fixture, reader-only inventory.

Only artificial Catalog metadata. No DEMIS/Oracle/medical data, DQA DB,
production credentials, Catalog import, activation, or legacy service writes.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from inventory_core import TABLES, collect_inventory

from app.db.catalog_bootstrap import ensure_catalog_schema
from app.db.session import get_catalog_session_factory
from app.models import catalog as legacy_catalog
from app.models import catalog_category as legacy_category
from app.models import catalog_history as legacy_history
from app.models import catalog_validation as legacy_validation
from tests.test_catalog_package_finalization import _create_fixture


OUTPUT = Path("/output")
READER = "u02c2_reader"
READER_PASSWORD = "synthetic_readonly_fixture_not_prod"
EXPECTED_DB = "u02b2b_catalog"
EXPECTED_HOST = "catalog-db"


def _guard():
    assert os.environ["CATALOG_DB_HOST"] == EXPECTED_HOST
    assert os.environ["CATALOG_DB_NAME"] == EXPECTED_DB
    assert os.environ["CATALOG_DB_USER"] == "u02b2b_user"
    assert os.environ["MEDICAL_DB_HOST"] == "non-existent-test-medical-host"
    assert OUTPUT.is_dir()
    assert Path("/legacy/backend/tests/test_catalog_package_finalization.py").is_file()


def _add_source_specific_rows(sid: int) -> None:
    fp = "b" * 64
    with get_catalog_session_factory()() as db:
        table = db.scalar(select(legacy_catalog.CatalogTable).where(
            legacy_catalog.CatalogTable.source_id == sid
        ))
        assert table is not None
        category = legacy_category.CatalogCategory(
            source_id=sid, category_key="ONLY_FIXTURE", category_name="Synthetic",
            description="artificial category", sort_order=1, active=True,
        )
        db.add(category)
        db.flush()
        db.add(legacy_category.CatalogTableCategory(
            table_id=table.id, category_id=category.id,
            is_primary=True, assignment_source="MANUAL",
            confidence=1.0, note="test",
        ))
        search = legacy_catalog.CatalogSearchDocument(
            source_id=sid, object_type="TABLE", table_id=table.id,
            column_id=None, document_key=f"synthetic-{sid}", searchable_text="SYNTHETIC ONLY",
            source_fingerprint=fp, document_fingerprint=fp, builder_version="u02c2-fixture",
            active=True,
        )
        db.add(search)
        db.flush()
        db.add(legacy_catalog.CatalogEmbeddingRun(
            source_id=sid, status="SUCCESS", model_key="synthetic-bge-m3",
            document_count=1, embedded_count=1, skipped_count=0, failed_count=0,
        ))
        db.add(legacy_catalog.CatalogEmbedding(
            search_document_id=search.id, model_key="synthetic-bge-m3",
            model_name="synthetic-fixture", model_revision="test",
            dimension=1024, normalized=True, document_fingerprint=fp,
            embedding=[0.0] * 1024,
        ))
        db.commit()


def _provision_restricted_reader():
    # PostgreSQL superuser/owner exists only in this throwaway container.
    # Reader has no DML grants and is the *only* connection used by collector.
    with get_catalog_session_factory()() as owner:
        with owner.begin():
            owner.execute(text(
                "CREATE ROLE u02c2_reader WITH LOGIN PASSWORD "
                "'synthetic_readonly_fixture_not_prod' NOSUPERUSER NOCREATEDB NOCREATEROLE"
            ))
            owner.execute(text("GRANT CONNECT ON DATABASE u02b2b_catalog TO u02c2_reader"))
            owner.execute(text("GRANT USAGE ON SCHEMA public TO u02c2_reader"))
            owner.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO u02c2_reader"))
            owner.execute(text("ALTER ROLE u02c2_reader SET default_transaction_read_only = on"))


def _models():
    names = (legacy_catalog, legacy_category, legacy_history, legacy_validation)
    models = {}
    for module in names:
        for value in vars(module).values():
            if isinstance(value, type) and hasattr(value, "__tablename__"):
                table_name = value.__tablename__
                if table_name in TABLES:
                    models[table_name] = value
    assert set(models) == set(TABLES)
    return models


def main():
    _guard()
    ensure_catalog_schema()
    source_1 = _create_fixture()
    source_2 = _create_fixture()
    _add_source_specific_rows(source_1)
    _provision_restricted_reader()

    url = URL.create(
        "postgresql+psycopg",
        username=READER, password=READER_PASSWORD, host=EXPECTED_HOST,
        port=5432, database=EXPECTED_DB,
    )
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    try:
        with Session(engine) as db:
            with db.begin():
                # Hard guard: exactly the expected disposable PG and a read-only TX.
                db.execute(text("SET TRANSACTION READ ONLY"))
                assert db.scalar(text("SELECT current_database()")) == EXPECTED_DB
                assert db.scalar(text("SELECT current_user")) == READER
                assert db.scalar(text("SELECT current_setting('transaction_read_only')")) == "on"
                assert db.scalar(text(
                    "SELECT has_table_privilege(current_user, 'public.catalog_source', 'INSERT')"
                )) is False
                result = collect_inventory(db, _models(), [source_1, source_2])
    finally:
        engine.dispose()

    assert len(result["sources"]) == 2
    first, second = result["sources"]
    assert first["table_counts"]["catalog_analysis_run"] == 2
    assert first["table_counts"]["catalog_analysis_snapshot"] == 2
    assert first["table_counts"]["catalog_category"] == 1
    assert first["table_counts"]["catalog_table_category"] == 1
    assert first["table_counts"]["catalog_search_document"] == 1
    assert first["table_counts"]["catalog_embedding_run"] == 1
    assert first["table_counts"]["catalog_embedding"] == 1
    assert second["table_counts"]["catalog_category"] == 0
    assert second["table_counts"]["catalog_embedding"] == 0

    (OUTPUT / "u02c2_inventory.json").write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    # Only status+counts printed; no source/Run ids, names, host, or values.
    print(json.dumps({
        "status": "PASS", "sources": len(result["sources"]),
        "allowlisted_tables": len(TABLES), "read_only": True,
        "crosswalk": "UNRESOLVED_PENDING_APPROVAL",
    }))


if __name__ == "__main__":
    main()
