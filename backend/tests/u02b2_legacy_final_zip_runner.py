"""Offline original Legacy finalizer runner for DQA U-02-B-2.

Run in an isolated Python process with PYTHONPATH=<pinned-legacy>/backend.
Only SQLAlchemy query descriptors are used; an in-memory synthetic Session
returns explicit fixture rows. No DB/Oracle/network/production state exists.
The original build_catalog_package and build_final_catalog_package functions
remain unmodified. Report, Preflight lookup and diff dependencies are stubbed
so this is *not* a report-rendering, live Preflight, or actual database test.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import sys
import types
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace as Row


SOURCE_ID = 1
WHEN = datetime(2026, 10, 15, tzinfo=timezone.utc)
FP = hashlib.sha256(b"u02b2-synthetic-legacy-run").hexdigest()
HOST = "U02B2_PRIVATE_HOST_SENTINEL"
USER = "U02B2_PRIVATE_USER_SENTINEL"
SECRET = "U02B2_PRIVATE_SECRET_SENTINEL"


def _row(**data):
    return Row(**data)


def _fixture():
    source = _row(
        id=SOURCE_ID, source_name="oracle_demis_mock", db_type="oracle",
        database_name="FREEPDB1", default_schema="DEMIS_OWNER",
        host=HOST, username=USER, encrypted_password=SECRET,
        connection_options={"private": SECRET},
    )
    run = _row(
        id=100, source_id=SOURCE_ID, status="SUCCESS", target_schema="DEMIS_OWNER",
        schema_fingerprint=FP, started_at=WHEN, finished_at=WHEN,
        table_count=2, column_count=5, relation_count=1, index_count=1,
    )
    snapshot = _row(
        id=101, source_id=SOURCE_ID, run_id=run.id,
        snapshot_version="1.0", capture_mode="ANALYSIS_API", created_at=WHEN,
        payload={
            "snapshot_version": "1.0",
            "source": {"source_name": source.source_name, "db_type": "oracle", "database_name": "FREEPDB1"},
            "schemas": ["DEMIS_OWNER"],
            "tables": [], "columns": [], "key_constraints": [], "foreign_keys": [], "indexes": [],
        },
    )
    tables = [
        _row(id=10, source_id=SOURCE_ID, schema_name="DEMIS_OWNER", table_name="PATIENT_REF",
             table_type="BASE TABLE", table_comment="synthetic patient reference",
             object_fingerprint=FP, active=True),
        _row(id=20, source_id=SOURCE_ID, schema_name="DEMIS_OWNER", table_name="VISIT_REF",
             table_type="BASE TABLE", table_comment="synthetic visit reference",
             object_fingerprint=FP, active=True),
    ]
    columns = []
    for col_id, table_id, ordinal, name, dtype in (
        (11, 10, 1, "PATIENT_ID", "VARCHAR2"),
        (12, 10, 2, "SITE_ID", "NUMBER"),
        (21, 20, 1, "PATIENT_ID", "VARCHAR2"),
        (22, 20, 2, "SITE_ID", "NUMBER"),
        (23, 20, 3, "VISIT_NOTE", "VARCHAR2"),
    ):
        columns.append(_row(
            id=col_id, table_id=table_id, ordinal_position=ordinal,
            column_name=name, data_type=dtype,
            character_maximum_length=30 if dtype == "VARCHAR2" else None,
            numeric_precision=8 if dtype == "NUMBER" else None,
            numeric_scale=0 if dtype == "NUMBER" else None,
            is_nullable=bool(col_id == 23), default_value=None,
            column_comment="synthetic metadata", is_primary_key=bool(table_id == 10),
            is_unique=False, object_fingerprint=FP, active=True,
        ))
    return source, run, snapshot, {
        "CatalogTable": tables,
        "CatalogColumn": columns,
        "CatalogKeyConstraint": [
            _row(id=30, table_id=10, constraint_name="PK_PATIENT", constraint_type="PRIMARY_KEY",
                 active=True),
        ],
        "CatalogKeyConstraintColumn": [
            _row(id=31, constraint_id=30, ordinal_position=1, column_id=11),
            _row(id=32, constraint_id=30, ordinal_position=2, column_id=12),
        ],
        "CatalogRelation": [
            _row(id=40, source_id=SOURCE_ID, source_table_id=20, target_table_id=10,
                 constraint_name="FK_VISIT_PATIENT", relation_type="FOREIGN_KEY",
                 object_fingerprint=FP, active=True),
        ],
        "CatalogRelationColumn": [
            _row(id=41, relation_id=40, ordinal_position=1, source_column_id=21, target_column_id=11),
            _row(id=42, relation_id=40, ordinal_position=2, source_column_id=22, target_column_id=12),
        ],
        "CatalogIndex": [
            _row(id=50, table_id=20, index_name="IDX_VISIT_PATIENT", is_unique=False,
                 index_method="BTREE", index_definition=None,
                 object_fingerprint=FP, active=True),
        ],
        "CatalogIndexColumn": [
            _row(id=51, index_id=50, ordinal_position=1, column_name="PATIENT_ID"),
            _row(id=52, index_id=50, ordinal_position=2, column_name="SITE_ID"),
        ],
        "CatalogCategory": [
            _row(id=60, source_id=SOURCE_ID, category_key="TEST_ONLY", category_name="Synthetic",
                 description="test fixture", sort_order=0, active=True),
        ],
        "CatalogTableCategory": [
            _row(id=61, table_id=20, category_id=60, is_primary=True,
                 assignment_source="MANUAL", confidence=1.0, note="fixture only"),
        ],
    }


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return list(self.rows)


class SyntheticLegacySession:
    """Minimal read-only Session double: no engine, database or commits."""

    def __init__(self, source, run, snapshot, rows):
        self.source = source
        self.run = run
        self.snapshot = snapshot
        self.rows = rows

    def get(self, model, source_id):
        assert model.__name__ == "CatalogSource" and source_id == SOURCE_ID
        return self.source

    def _entities(self, statement):
        return [item["entity"].__name__ for item in statement.column_descriptions]

    def scalars(self, statement):
        (name,) = self._entities(statement)
        if name not in self.rows:
            raise AssertionError(f"unexpected legacy model: {name}")
        return FakeResult(self.rows[name])

    def scalar(self, statement):
        (name,) = self._entities(statement)
        if name == "CatalogAnalysisRun":
            return self.run
        if name == "CatalogAnalysisSnapshot":
            return self.snapshot
        raise AssertionError(f"unexpected scalar model: {name}")

    def execute(self, statement):
        assert self._entities(statement) == ["CatalogAnalysisSnapshot", "CatalogAnalysisRun"]
        return FakeResult([(self.snapshot, self.run)])


def _preflight(status):
    return {
        "target_id": SOURCE_ID, "source_name": "oracle_demis_mock", "db_type": "oracle",
        "schemas": ["DEMIS_OWNER"], "status": status, "generated_at": WHEN.isoformat(),
        "connection": {"dbms_product": "Oracle", "db_version": "Synthetic",
                       "database_or_service": "FREEPDB1", "current_user": USER},
        "summary": {"tables": 2, "columns": 5},
        "checks": [{"key": "CONNECTION", "name": "Synthetic check", "status": "PASS",
                    "schema_name": "DEMIS_OWNER", "count": 2,
                    "detail": f"connected {USER} to {HOST}"}],
        "security": {"metadata_select_only": True, "business_data_selected": False},
    }


def run(status):
    assert status in {"WARNING", "READY"}
    # Only external, environment-dependent helpers are replaced. Both actual
    # legacy package writer and v2 finalizer are imported and invoked unchanged.
    report_module = types.ModuleType("app.services.catalog_report")
    report_module.REPORT_VERSION = "synthetic-test-only"
    report_module.build_db_analysis_report = lambda *_: _row(
        filename="fixture.docx", content=b"SYNTHETIC_REPORT_NOT_A_RENDERED_DOCX")
    sys.modules[report_module.__name__] = report_module
    preflight_module = types.ModuleType("app.services.catalog_validation_service")
    preflight_module.latest_preflight_result = lambda *_: _row(result_json=_preflight(status))
    sys.modules[preflight_module.__name__] = preflight_module
    diff_module = types.ModuleType("app.services.schema_diff_service")
    diff_module.compare_snapshot_payloads = lambda *_: (_ for _ in ()).throw(
        AssertionError("single-snapshot fixture cannot compare two runs"))
    sys.modules[diff_module.__name__] = diff_module

    from app.services.catalog_package_finalizer import build_final_catalog_package

    source, analysis_run, snapshot, rows = _fixture()
    result = build_final_catalog_package(
        SyntheticLegacySession(source, analysis_run, snapshot, rows), SOURCE_ID,
    )
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert "demis_catalog_package/manifest.json" in archive.namelist()
    return {
        "filename": result.filename,
        "manifest_readiness": result.manifest["package_readiness"],
        "archive_b64": base64.b64encode(result.content).decode("ascii"),
    }


if __name__ == "__main__":
    assert len(sys.argv) == 2
    print(json.dumps(run(sys.argv[1]), ensure_ascii=False, sort_keys=True))
