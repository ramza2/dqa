"""U-02-A subprocess fixture driver for an explicitly pinned legacy/DQA inspector.

This file is a runner, NOT a test and NOT production code. No database driver or
network connection is created: the supplied Engine-like object returns canned
Oracle dictionary rows and requires bound metadata-only SELECTs.
"""
from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from dataclasses import asdict


class Result:
    def __init__(self, conn, rows):
        self.conn = conn
        self.rows = rows

    def mappings(self):
        return self

    def __iter__(self):
        if not self.conn.connected:
            raise RuntimeError("CURSOR_CLOSED")
        return iter(self.rows)


def _fixture(kind):
    if kind == "empty":
        return {x: [] for x in ("tables", "columns", "pks", "uks", "fks", "indexes")}
    if kind not in ("rich", "changed_comment"):
        raise ValueError("unknown synthetic fixture")
    table_comment = "synthetic visit revised" if kind == "changed_comment" else "synthetic visit"
    column_comment = "synthetic id revised" if kind == "changed_comment" else "synthetic id"
    owner = "DEMIS_OWNER"
    return {
        "tables": [
            {"schema_name": owner, "table_name": "TB_PATIENT", "table_comment": "synthetic patient"},
            {"schema_name": owner, "table_name": "TB_VISIT", "table_comment": table_comment},
        ],
        "columns": [
            {"schema_name": owner, "table_name": "TB_PATIENT", "ordinal_position": 1,
             "column_name": "PATIENT_ID", "data_type": "VARCHAR2",
             "character_maximum_length": 30, "numeric_precision": None,
             "numeric_scale": None, "nullable": "N", "column_comment": column_comment},
            {"schema_name": owner, "table_name": "TB_PATIENT", "ordinal_position": 2,
             "column_name": "SITE_ID", "data_type": "NUMBER",
             "character_maximum_length": None, "numeric_precision": 5,
             "numeric_scale": 0, "nullable": "N", "column_comment": None},
            {"schema_name": owner, "table_name": "TB_VISIT", "ordinal_position": 1,
             "column_name": "PATIENT_ID", "data_type": "VARCHAR2",
             "character_maximum_length": 30, "numeric_precision": None,
             "numeric_scale": None, "nullable": "N", "column_comment": None},
        ],
        "pks": [
            {"schema_name": owner, "table_name": "TB_PATIENT",
             "constraint_name": "PK_PATIENT", "column_name": "PATIENT_ID",
             "ordinal_position": 1},
        ],
        "uks": [
            {"schema_name": owner, "table_name": "TB_PATIENT",
             "constraint_name": "UK_PATIENT_SITE", "column_name": "SITE_ID",
             "ordinal_position": 1},
        ],
        "fks": [
            {"constraint_name": "FK_VISIT_PATIENT", "source_schema": owner,
             "source_table": "TB_VISIT", "source_column": "SITE_ID",
             "target_schema": owner, "target_table": "TB_PATIENT",
             "target_column": "SITE_ID", "ordinal_position": 2},
            {"constraint_name": "FK_VISIT_PATIENT", "source_schema": owner,
             "source_table": "TB_VISIT", "source_column": "PATIENT_ID",
             "target_schema": owner, "target_table": "TB_PATIENT",
             "target_column": "PATIENT_ID", "ordinal_position": 1},
        ],
        "indexes": [
            {"schema_name": owner, "table_name": "TB_VISIT",
             "index_name": "IX_VISIT_PATIENT", "uniqueness": "NONUNIQUE",
             "index_type": "NORMAL", "column_name": "SITE_ID", "ordinal_position": 2},
            {"schema_name": owner, "table_name": "TB_VISIT",
             "index_name": "IX_VISIT_PATIENT", "uniqueness": "NONUNIQUE",
             "index_type": "NORMAL", "column_name": "PATIENT_ID", "ordinal_position": 1},
        ],
    }


class FakeEngine:
    def __init__(self, rows):
        self.rows = rows
        self.connected = False
        self.readonly_starts = 0
        self.calls = []

    @contextmanager
    def connect(self):
        assert not self.connected
        self.connected = True
        try:
            yield self
        finally:
            self.connected = False

    def exec_driver_sql(self, sql):
        assert self.connected and sql == "SET TRANSACTION READ ONLY"
        self.readonly_starts += 1

    def execute(self, statement, params):
        assert self.connected
        query = " ".join(str(statement).upper().split())
        assert query.startswith("SELECT ") and "FROM ALL_" in query
        assert all(token not in query for token in (
            " INSERT ", " UPDATE ", " DELETE ", " MERGE ", " DROP ", " ALTER ",
        ))
        self.calls.append(query)
        if "SELECT DISTINCT OWNER" in query:
            assert len(params) >= 2 and "SYS" in params.values()
            return Result(self, [{"owner": "DEMIS_OWNER"}, {"owner": "APP_OWNER"}])
        assert params == {"schema": "DEMIS_OWNER"}, params
        if "FROM ALL_TABLES T" in query:
            group = "tables"
        elif "FROM ALL_TAB_COLUMNS TC" in query:
            group = "columns"
        elif "FROM ALL_CONSTRAINTS C" in query:
            group = (
                "pks" if "CONSTRAINT_TYPE = 'P'" in query else
                "uks" if "CONSTRAINT_TYPE = 'U'" in query else
                "fks" if "CONSTRAINT_TYPE = 'R'" in query else None
            )
        elif "FROM ALL_INDEXES I" in query:
            group = "indexes"
        else:
            group = None
        assert group, "unexpected Oracle metadata SQL"
        return Result(self, self.rows[group])


def run(mode, kind):
    if mode == "legacy":
        from app.analyzers.oracle import OracleSchemaInspector
    elif mode == "dqa":
        from app.adapters.schema_inspector.oracle import OracleSchemaInspector
    else:
        raise ValueError("unknown inspector mode")

    engine = FakeEngine(_fixture(kind))
    inspector = OracleSchemaInspector(engine, "FREEPDB1")
    result = asdict(inspector.inspect("DEMIS_OWNER"))
    assert not engine.connected
    assert len(engine.calls) == 6
    result["foreign_keys"] = sorted(result["foreign_keys"], key=lambda x: x["constraint_name"])
    result["indexes"] = sorted(result["indexes"], key=lambda x: (x["table_name"], x["index_name"]))
    scan_readonly = engine.readonly_starts

    # Tests the known change: legacy returns streaming mappings after the
    # connection is closed, DQA consumes them inside its read-only transaction.
    try:
        discovered = inspector.list_schemas()
        schema_listing = {"status": "OK", "schemas": discovered}
    except RuntimeError as exc:
        if str(exc) != "CURSOR_CLOSED":
            raise
        schema_listing = {"status": "CURSOR_CLOSED"}
    assert not engine.connected
    assert len(engine.calls) == 7

    return {
        "snapshot": result,
        "inspect_queries": 6,
        "inspect_readonly_starts": scan_readonly,
        "total_readonly_starts": engine.readonly_starts,
        "schema_listing": schema_listing,
    }


if __name__ == "__main__":
    assert len(sys.argv) == 3
    print(json.dumps(run(sys.argv[1], sys.argv[2]), ensure_ascii=False, sort_keys=True))
