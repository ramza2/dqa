"""S-06-G: 25-table synthetic Oracle Dictionary -> v2 WARNING -> Discovery.

An expanded, deterministic metadata Gold fixture, NOT actual DEMIS tables or
clinical records. No DB, network, real credentials, approval, activation, LLM,
embedding calls, or db_session/db_client fixtures.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

from app.adapters.schema_inspector.oracle import OracleSchemaInspector
from app.models.catalog_import import CatalogImportRevision
from app.services.catalog_package_validation import validate_catalog_package_bytes
from app.services.data_discovery_document import build_documents_for_revision
from app.services.data_discovery_search.relation import expand_relations
from app.services.schema_catalog_candidate import build_catalog_v2_candidate
from app.services.schema_snapshot_diff import compare_schema_snapshots
from tests.u02_oracle_parity_runner import FakeEngine, _fixture


OWNER = "DEMIS_OWNER"
TIMESTAMP = datetime(2026, 10, 19, tzinfo=timezone.utc)
SOURCE_A = "s06g_expanded_gold_a"
SOURCE_B = "s06g_expanded_gold_b"
EXTERNAL_SCHEMA = "REFERENCE_OWNER"
EXTERNAL_TABLE = "TB_REFERENCE_ONLY"


def _dictionary_25(*, reverse_rows: bool = False):
    rows = deepcopy(_fixture("rich"))

    # Complete the existing U-02-A 2-column FK and matching parent UNIQUE.
    # This synthetic repair is intentionally local, not an Oracle adapter fix.
    rows["uks"][0]["ordinal_position"] = 2
    rows["uks"].append({
        "schema_name": OWNER, "table_name": "TB_PATIENT",
        "constraint_name": "UK_PATIENT_SITE", "column_name": "PATIENT_ID",
        "ordinal_position": 1,
    })
    rows["columns"].append({
        "schema_name": OWNER, "table_name": "TB_VISIT",
        "ordinal_position": 2, "column_name": "SITE_ID",
        "data_type": "NUMBER", "character_maximum_length": None,
        "numeric_precision": 5, "numeric_scale": 0,
        "nullable": "N", "column_comment": None,
    })

    # 2 canonical U-02-A tables + 23 fictional metadata tables = 25.
    # Each child has an ID PK, one outgoing FK and one single-column index.
    for n in range(23):
        table = f"TB_GOLD_{n:02d}"
        rows["tables"].append({
            "schema_name": OWNER, "table_name": table,
            "table_comment": f"Synthetic module {n:02d}",
        })
        rows["columns"].extend([
            {
                "schema_name": OWNER, "table_name": table,
                "ordinal_position": 1, "column_name": "RECORD_ID",
                "data_type": "NUMBER", "character_maximum_length": None,
                "numeric_precision": 10, "numeric_scale": 0,
                "nullable": "N", "column_comment": "Synthetic record key",
            },
            {
                "schema_name": OWNER, "table_name": table,
                "ordinal_position": 2, "column_name": "PATIENT_ID",
                "data_type": "VARCHAR2", "character_maximum_length": 30,
                "numeric_precision": None, "numeric_scale": None,
                "nullable": "Y", "column_comment": "Synthetic relation key",
            },
        ])
        rows["pks"].append({
            "schema_name": OWNER, "table_name": table,
            "constraint_name": f"PK_GOLD_{n:02d}",
            "column_name": "RECORD_ID", "ordinal_position": 1,
        })
        # One relation deliberately points to a reference-only external
        # Schema. It is structural metadata, never an access grant.
        external = n == 22
        rows["fks"].append({
            "constraint_name": f"FK_GOLD_{n:02d}_TARGET",
            "source_schema": OWNER, "source_table": table,
            "source_column": "PATIENT_ID",
            "target_schema": EXTERNAL_SCHEMA if external else OWNER,
            "target_table": EXTERNAL_TABLE if external else "TB_PATIENT",
            "target_column": "ID" if external else "PATIENT_ID",
            "ordinal_position": 1,
        })
        rows["indexes"].append({
            "schema_name": OWNER, "table_name": table,
            "index_name": f"IX_GOLD_{n:02d}_PATIENT",
            "uniqueness": "NONUNIQUE", "index_type": "NORMAL",
            "column_name": "PATIENT_ID", "ordinal_position": 1,
        })

    if reverse_rows:
        for group in rows.values():
            group.reverse()
    return rows


def _inspect_25(*, reverse_rows: bool = False):
    engine = FakeEngine(_dictionary_25(reverse_rows=reverse_rows))
    snapshot = OracleSchemaInspector(engine, "FREEPDB1").inspect(OWNER)
    assert len(engine.calls) == 6
    assert engine.readonly_starts == 1
    assert not engine.connected
    assert (snapshot.db_type, snapshot.database_name, snapshot.schema_name) == (
        "oracle", "FREEPDB1", OWNER,
    )
    return snapshot


def _candidate(snapshot, *, source=SOURCE_A):
    archive = build_catalog_v2_candidate(
        snapshot, source_name=source, generated_at=TIMESTAMP,
    )
    validated = validate_catalog_package_bytes(archive)
    assert validated.package_readiness == "WARNING"
    assert validated.activation_eligible is False
    assert validated.source.source_name == source
    return archive, validated


def _drafts(validated):
    # Unsaved in-memory object, deliberately WARNING; no PG Session/import.
    docs = validated.parsed_documents
    revision = CatalogImportRevision(
        id=101,
        source_name=validated.source.source_name,
        schema_fingerprint=validated.schema_fingerprint,
        package_readiness="WARNING",
        tables_json=docs["tables.json"],
        columns_json=docs["columns.json"],
        relations_json=docs["relations.json"],
        indexes_json=docs["indexes.json"],
        categories_json=docs["categories.json"],
    )
    return revision, build_documents_for_revision(revision)


def _keyed(drafts):
    keyed = {item.document_key: item for item in drafts}
    assert len(keyed) == len(drafts), "duplicate physical search-document key"
    return keyed


def test_25_table_inspector_v2_warning_and_75_discovery_documents():
    snapshot = _inspect_25()
    assert len(snapshot.tables) == 25
    assert len(snapshot.columns) == 50
    assert len(snapshot.primary_keys) == 24
    assert len(snapshot.foreign_keys) == 24
    assert len(snapshot.indexes) == 24
    archive, validated = _candidate(snapshot)
    assert archive
    assert validated.counts["tables"] == 25
    assert validated.counts["columns"] == 50
    assert validated.counts["relations"] == 24
    assert validated.counts["indexes"] == 24
    revision, drafts = _drafts(validated)
    assert revision.package_readiness == "WARNING"
    assert len(drafts) == 75
    keys = _keyed(drafts)
    assert "TABLE:DEMIS_OWNER.TB_VISIT" in keys
    assert "COLUMN:DEMIS_OWNER.TB_GOLD_00.RECORD_ID" in keys
    assert "COLUMN:DEMIS_OWNER.TB_GOLD_22.PATIENT_ID" in keys
    assert all(
        (item.source_name, item.catalog_revision_id, item.schema_fingerprint)
        == (SOURCE_A, revision.id, validated.schema_fingerprint)
        for item in drafts
    )
    # Reference-only external object is not materialized as an own table.
    assert f"TABLE:{EXTERNAL_SCHEMA}.{EXTERNAL_TABLE}" not in keys
    external = expand_relations(
        revision, seed_tables=[(OWNER, "TB_GOLD_22")], max_hops=1,
    )
    assert [(x.schema_name, x.table_name) for x in external] == [
        (EXTERNAL_SCHEMA, EXTERNAL_TABLE),
    ]
    assert external[0].path[0].to_columns == ("ID",)
    assert external[0].path[0].direction == "outbound"


def test_25_table_unordered_oracle_rows_do_not_change_diff_zip_or_documents():
    first = _inspect_25()
    reversed_rows = _inspect_25(reverse_rows=True)
    diff = compare_schema_snapshots(first, reversed_rows)
    assert diff.identical and diff.total_changes == 0
    a, va = _candidate(first)
    b, vb = _candidate(reversed_rows)
    assert a == b
    assert va.schema_fingerprint == vb.schema_fingerprint == diff.target_fingerprint
    _, da = _drafts(va)
    _, db = _drafts(vb)
    assert {
        key: (d.source_fingerprint, d.document_fingerprint, d.searchable_text)
        for key, d in _keyed(da).items()
    } == {
        key: (d.source_fingerprint, d.document_fingerprint, d.searchable_text)
        for key, d in _keyed(db).items()
    }


def test_one_table_comment_drift_changes_only_local_table_and_its_columns():
    baseline = _inspect_25()
    current = deepcopy(baseline)
    target = "TB_GOLD_07"
    current.tables = [
        replace(table, table_comment="Synthetic module revised")
        if table.table_name == target else table
        for table in current.tables
    ]
    diff = compare_schema_snapshots(baseline, current)
    assert [(x.object_type, x.change_type, x.object_key, x.changed_fields)
            for x in diff.changes] == [
        ("TABLE", "CHANGED", (OWNER, target), ("table_comment",)),
    ]
    _, va = _candidate(baseline)
    _, vb = _candidate(current)
    assert va.schema_fingerprint != vb.schema_fingerprint
    assert va.schema_fingerprint == diff.base_fingerprint
    assert vb.schema_fingerprint == diff.target_fingerprint
    _, before = _drafts(va)
    _, after = _drafts(vb)
    old, new = _keyed(before), _keyed(after)
    assert set(old) == set(new)
    changed_keys = {
        key for key in old
        if old[key].document_fingerprint != new[key].document_fingerprint
    }
    assert changed_keys == {
        f"TABLE:{OWNER}.{target}",
        f"COLUMN:{OWNER}.{target}.RECORD_ID",
        f"COLUMN:{OWNER}.{target}.PATIENT_ID",
    }


def test_missing_one_index_is_explicit_drift_and_only_one_document_changes():
    original = _inspect_25()
    changed = deepcopy(original)
    changed.indexes = [
        idx for idx in changed.indexes
        if idx.index_name != "IX_GOLD_15_PATIENT"
    ]
    diff = compare_schema_snapshots(original, changed)
    assert [(x.object_type, x.change_type, x.object_key)
            for x in diff.changes] == [
        ("INDEX", "REMOVED", (OWNER, "TB_GOLD_15", "IX_GOLD_15_PATIENT")),
    ]
    _, va = _candidate(original)
    _, vb = _candidate(changed)
    assert va.schema_fingerprint != vb.schema_fingerprint
    _, before = _drafts(va)
    _, after = _drafts(vb)
    old, new = _keyed(before), _keyed(after)
    assert {
        key for key in old
        if old[key].document_fingerprint != new[key].document_fingerprint
    } == {f"TABLE:{OWNER}.TB_GOLD_15"}
    assert vb.package_readiness == "WARNING" and not vb.activation_eligible


def test_same_physical_25_table_schema_in_two_sources_preserves_source_isolation():
    snapshot = _inspect_25()
    a, va = _candidate(snapshot, source=SOURCE_A)
    b, vb = _candidate(snapshot, source=SOURCE_B)
    assert a != b  # Source-specific manifest and package bytes
    assert va.schema_fingerprint == vb.schema_fingerprint
    assert va.source.source_name != vb.source.source_name
    _, da = _drafts(va)
    _, db = _drafts(vb)
    ma, mb = _keyed(da), _keyed(db)
    assert set(ma) == set(mb)
    assert all(ma[k].source_name == SOURCE_A for k in ma)
    assert all(mb[k].source_name == SOURCE_B for k in mb)
    assert {
        k: (d.searchable_text, d.document_fingerprint)
        for k, d in ma.items()
    } == {
        k: (d.searchable_text, d.document_fingerprint)
        for k, d in mb.items()
    }
