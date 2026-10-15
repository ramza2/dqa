"""U-02-C-3: compare source and restored disposable PostgreSQL catalog evidence.

Only the pinned synthetic Legacy Catalog schema is accessed.
All DB sessions use the U-02-C-2 SELECT-only role and REPEATABLE READ/READ ONLY.
Counts, run/source links and *all rows' digests* are compared; raw values,
DB identities, credentials and vectors never leave this container.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from fixture import _models, READER, READER_PASSWORD, EXPECTED_DB, EXPECTED_HOST
from inventory_core import TABLES, collect_inventory

OUTPUT = Path("/output")
RESTORE_DB = "u02c3_restore"


def _connect(dbname: str):
    assert dbname in (EXPECTED_DB, RESTORE_DB)
    return create_engine(
        URL.create(
            "postgresql+psycopg", username=READER, password=READER_PASSWORD,
            host=EXPECTED_HOST, port=5432, database=dbname,
        ),
        pool_pre_ping=True, connect_args={"connect_timeout": 5},
    )


def _observe(dbname: str):
    engine = _connect(dbname)
    try:
        with Session(engine) as session:
            with session.begin():
                session.execute(text(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                ))
                assert session.scalar(text("SELECT current_database()")) == dbname
                assert session.scalar(text("SELECT current_user")) == READER
                assert session.scalar(text(
                    "SELECT current_setting('transaction_read_only')"
                )) == "on"
                assert session.scalar(text(
                    "SELECT current_setting('transaction_isolation')"
                )) == "repeatable read"
                assert session.scalar(text(
                    "SELECT has_table_privilege(current_user, "
                    "'public.catalog_source', 'INSERT')"
                )) is False
                assert session.scalar(text(
                    "SELECT has_database_privilege(current_user, "
                    "current_database(), 'CREATE')"
                )) is False

                models = _models()
                source = models["catalog_source"]
                fixture_ids = list(session.scalars(
                    select(source.id)
                    .where(source.source_name.startswith("final_package_"))
                    .order_by(source.id)
                ))
                assert len(fixture_ids) == 2
                inventory = collect_inventory(session, models, fixture_ids)

                # Fixed allowlist only, and entire table contents rather than
                # counts alone. Hashes never enter persisted evidence.
                signatures = {}
                for table in (*TABLES, "catalog_meta"):
                    assert table in (*TABLES, "catalog_meta")
                    key = "meta_key" if table == "catalog_meta" else "id"
                    query = text(
                        "SELECT count(*), "
                        "md5(coalesce(string_agg(md5(row_to_json(t)::text), "
                        f"'' ORDER BY t.{key}), '')) "
                        f"FROM public.{table} AS t"
                    )
                    row = session.execute(query).one()
                    signatures[table] = (row[0], row[1])
                return inventory, signatures
    finally:
        engine.dispose()


def main():
    expected = json.loads((OUTPUT / "u02c2_inventory.json").read_text("utf-8"))
    original, original_sig = _observe(EXPECTED_DB)
    restored, restored_sig = _observe(RESTORE_DB)

    assert original == expected, "ORIGINAL_INVENTORY_CHANGED"
    assert restored == original, "RESTORED_INVENTORY_DIFFERS"
    assert set(original_sig) == set(TABLES) | {"catalog_meta"}
    assert original_sig == restored_sig, "RESTORED_ROW_DIGEST_MISMATCH"
    assert all(count >= 0 for count, _ in original_sig.values())

    result = {
        "evidence_kind": "U02C3_SYNTHETIC_PG_RESTORE_ONLY",
        "original_inventory_equal": True,
        "restored_inventory_equal": True,
        "row_digest_equal": True,
        "checked_tables": len(TABLES),
        "checked_extra_tables": 1,
        "source_count": 2,
        "reader_role": "SELECT_ONLY",
        "transaction": "REPEATABLE_READ_READ_ONLY",
        "dqa_catalog_modified": False,
        "dqa_import_revision_id": None,
        "dqa_active_catalog_modified": False,
        "cutover_allowed": False,
        "rollback_authorized": False,
    }
    (OUTPUT / "restore_verified.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS", "restored_database_verified": True,
        "tables": len(TABLES), "sources": 2,
        "row_digest_equal": True, "cutover_allowed": False,
    }))


if __name__ == "__main__":
    main()
