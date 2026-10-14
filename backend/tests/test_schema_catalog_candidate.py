"""Pure Schema Inspector -> Catalog v2 candidate tests; no database or API."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone

import pytest

from app.adapters.schema_inspector.base import (
    InspectedColumn,
    InspectedForeignKey,
    InspectedForeignKeyColumn,
    InspectedIndex,
    InspectedIndexColumn,
    InspectedPrimaryKey,
    InspectedTable,
    InspectedUniqueConstraint,
    SchemaSnapshot,
)
from app.services.catalog_package_validation import validate_catalog_package_bytes
from app.services.catalog_query import (
    _map_column, _map_index, _map_relation, _map_table,
)
from app.services.schema_catalog_candidate import build_catalog_v2_candidate


TIMESTAMP = datetime(2026, 10, 14, 2, 0, tzinfo=timezone.utc)


def _snapshot() -> SchemaSnapshot:
    def col(table, ordinal, name, nullable=True, default=None):
        return InspectedColumn(
            schema_name="DEMIS_OWNER", table_name=table,
            ordinal_position=ordinal, column_name=name, data_type="VARCHAR2",
            character_maximum_length=32, numeric_precision=None, numeric_scale=None,
            is_nullable=nullable, default_value=default, column_comment="Synthetic",
        )
    return SchemaSnapshot(
        db_type="oracle", database_name="FREEPDB1", schema_name="DEMIS_OWNER",
        tables=[
            InspectedTable("DEMIS_OWNER", "TB_PARENT", "BASE TABLE", "부모 테이블"),
            InspectedTable("DEMIS_OWNER", "TB_CHILD", "BASE TABLE", "자식 테이블"),
        ],
        columns=[
            col("TB_PARENT", 1, "ID", nullable=False),
            col("TB_CHILD", 1, "ID", nullable=False),
            col("TB_CHILD", 2, "PARENT_ID", default="sensitive-default-here"),
            col("TB_CHILD", 3, "AREA_ID"),
            col("TB_CHILD", 4, "CODE"),
        ],
        primary_keys=[
            InspectedPrimaryKey("DEMIS_OWNER", "TB_PARENT", "PK_PARENT", "ID", 1),
            InspectedPrimaryKey("DEMIS_OWNER", "TB_CHILD", "PK_CHILD", "ID", 1),
        ],
        unique_constraints=[
            InspectedUniqueConstraint("DEMIS_OWNER", "TB_CHILD", "UK_CHILD_COMPOSITE", "AREA_ID", 1),
            InspectedUniqueConstraint("DEMIS_OWNER", "TB_CHILD", "UK_CHILD_COMPOSITE", "CODE", 2),
            InspectedUniqueConstraint("DEMIS_OWNER", "TB_CHILD", "UK_CHILD_CODE", "CODE", 1),
        ],
        foreign_keys=[
            InspectedForeignKey(
                schema_name="DEMIS_OWNER", constraint_name="FK_CHILD_PARENT",
                source_table="TB_CHILD", target_schema="DEMIS_OWNER", target_table="TB_PARENT",
                columns=(
                    InspectedForeignKeyColumn(2, "AREA_ID", "ID"),
                    InspectedForeignKeyColumn(1, "PARENT_ID", "ID"),
                ),
            ),
        ],
        indexes=[
            InspectedIndex(
                schema_name="DEMIS_OWNER", table_name="TB_CHILD",
                index_name="IX_CHILD_PARENT", is_unique=False,
                index_method="NORMAL", index_definition="sensitive-index-expression-here",
                columns=(
                    InspectedIndexColumn(2, "AREA_ID"),
                    InspectedIndexColumn(1, "PARENT_ID"),
                ),
            ),
        ],
    )


def test_candidate_is_valid_v2_warning_and_never_activatable():
    output = build_catalog_v2_candidate(
        _snapshot(), source_name="oracle_demis_mock", generated_at=TIMESTAMP
    )
    validated = validate_catalog_package_bytes(output)
    assert validated.package_format == "demis-catalog-package"
    assert validated.package_version == "2.0"
    assert validated.package_readiness == "WARNING"
    assert validated.activation_eligible is False
    assert validated.source.source_name == "oracle_demis_mock"
    assert validated.source.default_schema == "DEMIS_OWNER"
    assert validated.counts["tables"] == 2
    assert validated.counts["columns"] == 5
    assert validated.counts["relations"] == 1
    assert validated.counts["indexes"] == 1
    assert validated.files_validated == 11


def test_candidate_preserves_physical_metadata_and_catalog_query_shapes():
    output = build_catalog_v2_candidate(
        _snapshot(), source_name="oracle_demis_mock", generated_at=TIMESTAMP
    )
    parsed = validate_catalog_package_bytes(output).parsed_documents
    tables = parsed["tables.json"]["tables"]
    columns = parsed["columns.json"]["columns"]
    rel = parsed["relations.json"]["relations"][0]
    idx = parsed["indexes.json"]["indexes"][0]

    assert len(tables) == 2
    assert _map_table(tables[1], {}).comment == "부모 테이블"
    items = [_map_column(c) for c in columns]
    by_name = {item.name: item for item in items if item.table_name == "TB_CHILD"}
    assert by_name["ID"].is_primary_key is True
    assert by_name["PARENT_ID"].is_primary_key is False
    assert by_name["AREA_ID"].is_unique is False
    assert by_name["CODE"].is_unique is True
    assert by_name["ID"].nullable is False
    assert by_name["PARENT_ID"].comment == "Synthetic"

    mapped_rel = _map_relation(rel)
    assert mapped_rel.name == "FK_CHILD_PARENT"
    assert mapped_rel.referenced_table_name == "TB_PARENT"
    assert [(x.column, x.referenced_column) for x in mapped_rel.columns] == [
        ("PARENT_ID", "ID"), ("AREA_ID", "ID"),
    ]
    mapped_idx = _map_index(idx)
    assert mapped_idx.name == "IX_CHILD_PARENT"
    assert mapped_idx.columns == ["PARENT_ID", "AREA_ID"]
    assert mapped_idx.unique is False


def test_candidate_fingerprint_matches_all_required_documents():
    output = build_catalog_v2_candidate(
        _snapshot(), source_name="oracle_demis_mock", generated_at=TIMESTAMP
    )
    validated = validate_catalog_package_bytes(output)
    fp = validated.schema_fingerprint
    assert len(fp) == 64
    assert validated.parsed_documents["database.json"]["latest_analysis"]["schema_fingerprint"] == fp
    assert validated.parsed_documents["analysis/latest_run.json"]["run"]["schema_fingerprint"] == fp
    assert validated.parsed_documents["analysis/schema_snapshot.json"]["payload"]["schema_fingerprint"] == fp


def test_same_snapshot_and_timestamp_yield_identical_package():
    a = _snapshot()
    b = _snapshot()
    b.tables.reverse()
    b.columns.reverse()
    b.primary_keys.reverse()
    b.unique_constraints.reverse()
    b.indexes.reverse()
    assert build_catalog_v2_candidate(a, source_name="mock", generated_at=TIMESTAMP) == (
        build_catalog_v2_candidate(b, source_name="mock", generated_at=TIMESTAMP)
    )


def test_changed_physical_comment_changes_fingerprint():
    a = _snapshot()
    b = _snapshot()
    b.tables[0] = InspectedTable(
        "DEMIS_OWNER", "TB_PARENT", "BASE TABLE", "수정된 주석"
    )
    av = validate_catalog_package_bytes(
        build_catalog_v2_candidate(a, source_name="mock", generated_at=TIMESTAMP)
    )
    bv = validate_catalog_package_bytes(
        build_catalog_v2_candidate(b, source_name="mock", generated_at=TIMESTAMP)
    )
    assert av.schema_fingerprint != bv.schema_fingerprint


def test_does_not_export_default_sql_index_sql_or_connection_secrets():
    output = build_catalog_v2_candidate(
        _snapshot(), source_name="mock", generated_at=TIMESTAMP
    )
    with zipfile.ZipFile(io.BytesIO(output)) as zf:
        joined = b"".join(zf.read(n) for n in zf.namelist())
    assert b"sensitive-default-here" not in joined
    assert b"sensitive-index-expression-here" not in joined
    assert b"password" not in joined.lower()
    assert b"fake-inspector-host" not in joined
    docs = validate_catalog_package_bytes(output).parsed_documents
    assert docs["validation/preflight.json"]["available"] is False
    assert docs["diff/latest.json"]["available"] is False


@pytest.mark.parametrize("source", ["", " bad", "bad/name", "../bad", "bad\\name"])
def test_reject_unsafe_source_name(source):
    with pytest.raises(ValueError):
        build_catalog_v2_candidate(_snapshot(), source_name=source, generated_at=TIMESTAMP)


def test_reject_empty_or_unsupported_snapshots():
    with pytest.raises(ValueError):
        build_catalog_v2_candidate(
            SchemaSnapshot(db_type="oracle", database_name="FREEPDB1",
                           schema_name="DEMIS_OWNER"),
            source_name="mock", generated_at=TIMESTAMP,
        )
    snap = _snapshot()
    snap.db_type = "postgresql"
    with pytest.raises(ValueError):
        build_catalog_v2_candidate(snap, source_name="mock", generated_at=TIMESTAMP)


def test_requires_timezone_aware_generated_at():
    with pytest.raises(ValueError):
        build_catalog_v2_candidate(
            _snapshot(), source_name="mock",
            generated_at=datetime(2026, 10, 14, 2, 0)
        )
