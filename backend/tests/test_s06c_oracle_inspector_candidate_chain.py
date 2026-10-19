"""S-06-C: Oracle dictionary fake -> Inspector -> Diff -> v2 WARNING package.

A cross-layer, synthetic-only regression. No live Oracle, PostgreSQL, LLM,
MCP, application API, activation, clinical rows or legacy service is touched.
The existing U-02-A dictionary fixture is the explicit input, not G1 evidence.
"""

from __future__ import annotations

import io
import json
import zipfile
from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.adapters.schema_inspector.oracle import OracleSchemaInspector
from app.services.catalog_package_validation import validate_catalog_package_bytes
from app.services.schema_catalog_candidate import build_catalog_v2_candidate
from app.services.schema_snapshot_diff import compare_schema_snapshots
from tests.u02_oracle_parity_runner import FakeEngine, _fixture


TIMESTAMP = datetime(2026, 10, 19, 0, 0, tzinfo=timezone.utc)
SOURCE = "s06c_synthetic_oracle"


def _inspect(kind: str = "rich", *, reversed_rows: bool = False):
    rows = deepcopy(_fixture(kind))
    # The original U-02-A dictionary parity fixture tests adapter equivalence;
    # complete TB_VISIT's referenced composite-FK source columns before using
    # it for the strict v2 catalog contract. Never patch production adapters.
    rows["columns"].append({
        "schema_name": "DEMIS_OWNER", "table_name": "TB_VISIT",
        "ordinal_position": 2, "column_name": "SITE_ID",
        "data_type": "NUMBER", "character_maximum_length": None,
        "numeric_precision": 5, "numeric_scale": 0,
        "nullable": "N", "column_comment": None,
    })
    if reversed_rows:
        for items in rows.values():
            items.reverse()

    engine = FakeEngine(rows)
    snapshot = OracleSchemaInspector(engine, "FREEPDB1").inspect("DEMIS_OWNER")
    assert len(engine.calls) == 6
    assert engine.readonly_starts == 1
    assert not engine.connected
    assert snapshot.db_type == "oracle"
    assert snapshot.database_name == "FREEPDB1"
    assert snapshot.schema_name == "DEMIS_OWNER"
    return snapshot


def _candidate(snapshot):
    archive = build_catalog_v2_candidate(
        snapshot, source_name=SOURCE, generated_at=TIMESTAMP,
    )
    result = validate_catalog_package_bytes(archive)
    assert result.package_readiness == "WARNING"
    assert result.activation_eligible is False
    return archive, result


def test_inspector_snapshot_to_warning_candidate_has_matching_fingerprint():
    snapshot = _inspect()
    assert len(snapshot.tables) == 2
    assert len(snapshot.columns) == 4
    assert len(snapshot.foreign_keys) == 1
    assert [
        (col.ordinal_position, col.source_column, col.target_column)
        for col in snapshot.foreign_keys[0].columns
    ] == [(1, "PATIENT_ID", "PATIENT_ID"), (2, "SITE_ID", "SITE_ID")]
    assert [
        (col.ordinal_position, col.column_name)
        for col in snapshot.indexes[0].columns
    ] == [(1, "PATIENT_ID"), (2, "SITE_ID")]

    package, validation = _candidate(snapshot)
    diff = compare_schema_snapshots(snapshot, deepcopy(snapshot))
    assert diff.identical and diff.total_changes == 0
    assert validation.schema_fingerprint == diff.target_fingerprint

    # A WARNING manifest is a validated candidate, not a trusted READY grant.
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        name = next(n for n in archive.namelist() if n.endswith("/manifest.json"))
        manifest = json.loads(archive.read(name))
    assert manifest["package_readiness"] == "WARNING"
    assert manifest["security"]["metadata_select_only"] is True
    assert manifest["security"]["business_data_selected"] is False
    assert manifest["security"]["credentials_exported"] is False
    assert manifest["security"]["connection_host_exported"] is False
    assert manifest["schema_fingerprint"] == validation.schema_fingerprint


def test_dictionary_comment_change_is_visible_in_diff_and_candidate():
    previous = _inspect("rich")
    changed = _inspect("changed_comment")
    diff = compare_schema_snapshots(previous, changed)
    assert diff.identical is False
    assert diff.total_changes == 2
    assert {
        (item.object_type, item.object_key, item.changed_fields)
        for item in diff.changes
    } == {
        ("TABLE", ("DEMIS_OWNER", "TB_VISIT"), ("table_comment",)),
        ("COLUMN", ("DEMIS_OWNER", "TB_PATIENT", "PATIENT_ID"), ("column_comment",)),
    }
    _, prev_validation = _candidate(previous)
    _, changed_validation = _candidate(changed)
    assert prev_validation.schema_fingerprint == diff.base_fingerprint
    assert changed_validation.schema_fingerprint == diff.target_fingerprint
    assert prev_validation.schema_fingerprint != changed_validation.schema_fingerprint
    assert changed_validation.activation_eligible is False


def test_dictionary_row_order_is_not_schema_drift():
    original = _inspect()
    permuted = _inspect(reversed_rows=True)
    diff = compare_schema_snapshots(original, permuted)
    assert diff.identical
    assert diff.total_changes == 0
    assert diff.base_fingerprint == diff.target_fingerprint
    _, before = _candidate(original)
    _, after = _candidate(permuted)
    assert before.schema_fingerprint == after.schema_fingerprint


def test_cross_target_and_missing_baseline_never_count_as_parity():
    original = _inspect()
    different = deepcopy(original)
    different.database_name = "ANOTHER_SYNTHETIC_DB"
    with pytest.raises(ValueError, match="cross-target"):
        compare_schema_snapshots(original, different)
    with pytest.raises(TypeError, match="two SchemaSnapshot"):
        compare_schema_snapshots(None, original)
