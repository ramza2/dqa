"""Isolated, synthetic Oracle ALL_* inspector tests; no Oracle credentials/DB access."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from app.adapters.schema_inspector.base import SchemaSnapshot, merge_snapshots
from app.adapters.schema_inspector.oracle import (
    OracleSchemaInspector,
    SYSTEM_SCHEMAS,
)


class FakeResult:
    def __init__(self, owner, rows):
        self.owner = owner
        self.rows = rows

    def mappings(self):
        return self

    def __iter__(self):
        assert self.owner.connected, "result must be consumed before connection closes"
        return iter(self.rows)


class FakeConnection:
    def __init__(self):
        self.connected = False
        self.calls = []

    @contextmanager
    def connect(self):
        self.connected = True
        try:
            yield self
        finally:
            self.connected = False

    def execute(self, statement, parameters):
        sql = str(statement)
        normalized = " ".join(sql.split()).upper()
        self.calls.append((normalized, dict(parameters)))
        assert normalized.startswith("SELECT ")
        assert not any(token in normalized for token in (
            " INSERT ", " UPDATE ", " DELETE ", " DROP ", " ALTER ",
        ))
        assert "FROM ALL_" in normalized
        if "SELECT DISTINCT OWNER" in normalized:
            return FakeResult(self, [{"owner": "DEMIS_OWNER"}, {"owner": "APP_OWNER"}])
        assert parameters == {"schema": "DEMIS_OWNER"}
        assert ":SCHEMA" in normalized

        if "FROM ALL_TABLES T" in normalized:
            return FakeResult(self, [{
                "schema_name": "DEMIS_OWNER",
                "table_name": "TB_PATIENT",
                "table_comment": "Synthetic patient table",
            }])
        if "FROM ALL_TAB_COLUMNS TC" in normalized:
            return FakeResult(self, [
                {
                    "schema_name": "DEMIS_OWNER", "table_name": "TB_PATIENT",
                    "ordinal_position": 1, "column_name": "PATIENT_ID",
                    "data_type": "VARCHAR2",
                    "character_maximum_length": 20, "numeric_precision": None,
                    "numeric_scale": None, "nullable": "N",
                    "column_comment": "Synthetic identifier",
                },
                {
                    "schema_name": "DEMIS_OWNER", "table_name": "TB_PATIENT",
                    "ordinal_position": 2, "column_name": "AGE",
                    "data_type": "NUMBER",
                    "character_maximum_length": None, "numeric_precision": 3,
                    "numeric_scale": 0, "nullable": "Y",
                    "column_comment": None,
                },
            ])
        if "FROM ALL_CONSTRAINTS C" in normalized and "CONSTRAINT_TYPE = 'P'" in normalized:
            return FakeResult(self, [{
                "schema_name": "DEMIS_OWNER", "table_name": "TB_PATIENT",
                "constraint_name": "PK_PATIENT", "column_name": "PATIENT_ID",
                "ordinal_position": 1,
            }])
        if "FROM ALL_CONSTRAINTS C" in normalized and "CONSTRAINT_TYPE = 'U'" in normalized:
            return FakeResult(self, [{
                "schema_name": "DEMIS_OWNER", "table_name": "TB_PATIENT",
                "constraint_name": "UK_PATIENT", "column_name": "AGE",
                "ordinal_position": 1,
            }])
        if "FROM ALL_CONSTRAINTS C" in normalized and "CONSTRAINT_TYPE = 'R'" in normalized:
            return FakeResult(self, [
                {
                    "constraint_name": "FK_VISIT_PATIENT",
                    "source_schema": "DEMIS_OWNER", "source_table": "TB_VISIT",
                    "source_column": "SITE_ID", "target_schema": "DEMIS_OWNER",
                    "target_table": "TB_PATIENT", "target_column": "SITE_ID",
                    "ordinal_position": 2,
                },
                {
                    "constraint_name": "FK_VISIT_PATIENT",
                    "source_schema": "DEMIS_OWNER", "source_table": "TB_VISIT",
                    "source_column": "PATIENT_ID", "target_schema": "DEMIS_OWNER",
                    "target_table": "TB_PATIENT", "target_column": "PATIENT_ID",
                    "ordinal_position": 1,
                },
            ])
        if "FROM ALL_INDEXES I" in normalized:
            return FakeResult(self, [
                {
                    "schema_name": "DEMIS_OWNER", "table_name": "TB_VISIT",
                    "index_name": "IX_VISIT_PATIENT", "uniqueness": "NONUNIQUE",
                    "index_type": "NORMAL", "column_name": "SITE_ID",
                    "ordinal_position": 2,
                },
                {
                    "schema_name": "DEMIS_OWNER", "table_name": "TB_VISIT",
                    "index_name": "IX_VISIT_PATIENT", "uniqueness": "NONUNIQUE",
                    "index_type": "NORMAL", "column_name": "PATIENT_ID",
                    "ordinal_position": 1,
                },
            ])
        raise AssertionError("unexpected metadata SQL")


def test_oracle_inspector_collects_metadata_only_and_binds_schema():
    engine = FakeConnection()
    inspector = OracleSchemaInspector(engine, "FREEPDB1")

    snapshot = inspector.inspect("DEMIS_OWNER")

    assert isinstance(snapshot, SchemaSnapshot)
    assert snapshot.db_type == "oracle"
    assert snapshot.schema_name == "DEMIS_OWNER"
    assert snapshot.database_name == "FREEPDB1"
    assert [t.table_name for t in snapshot.tables] == ["TB_PATIENT"]
    assert snapshot.tables[0].table_comment == "Synthetic patient table"
    assert [c.column_name for c in snapshot.columns] == ["PATIENT_ID", "AGE"]
    assert snapshot.columns[0].is_nullable is False
    assert snapshot.columns[1].is_nullable is True
    assert snapshot.columns[1].numeric_precision == 3
    assert snapshot.columns[0].default_value is None  # Oracle LONG not fetched
    assert snapshot.primary_keys[0].constraint_name == "PK_PATIENT"
    assert snapshot.unique_constraints[0].column_name == "AGE"
    assert [c.source_column for c in snapshot.foreign_keys[0].columns] == [
        "PATIENT_ID", "SITE_ID",
    ]
    assert [c.column_name for c in snapshot.indexes[0].columns] == [
        "PATIENT_ID", "SITE_ID",
    ]
    assert len(engine.calls) == 6
    assert not engine.connected
    for sql, params in engine.calls:
        assert params == {"schema": "DEMIS_OWNER"}
        assert ":SCHEMA" in sql


def test_schema_list_consumes_result_inside_connection_and_binds_system_names():
    engine = FakeConnection()
    schemas = OracleSchemaInspector(engine, "FREEPDB1").list_schemas()
    assert schemas == ["DEMIS_OWNER", "APP_OWNER"]
    assert not engine.connected
    assert len(engine.calls) == 1
    sql, params = engine.calls[0]
    assert "OWNER NOT IN" in sql
    assert set(params.values()) == set(SYSTEM_SCHEMAS)
    assert all(name not in sql for name in ("'SYS'", "'SYSTEM'"))


@pytest.mark.parametrize("schema", [
    "", " ", " SYS", "SYS", "sys", "SYSTEM",
    " DEMIS_OWNER", "DEMIS_OWNER ", "x" * 129, None,
])
def test_invalid_or_system_schema_rejected_before_connection(schema):
    engine = FakeConnection()
    with pytest.raises(ValueError):
        OracleSchemaInspector(engine, "FREEPDB1").inspect(schema)
    assert engine.calls == []


def test_merge_snapshot_empty_and_multi_schema():
    with pytest.raises(ValueError):
        merge_snapshots([])
    ins = OracleSchemaInspector(FakeConnection(), "FREEPDB1")
    first = ins.inspect("DEMIS_OWNER")
    second = SchemaSnapshot(db_type="oracle", database_name="FREEPDB1", schema_name="APP_OWNER")
    merged = merge_snapshots([first, second])
    assert merged.schema_name == "APP_OWNER,DEMIS_OWNER"
    assert len(merged.tables) == len(first.tables)
