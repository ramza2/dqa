"""Synthetic, metadata-only SchemaSnapshot Diff foundation tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
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
from app.services.schema_catalog_candidate import build_catalog_v2_candidate
from app.services.schema_snapshot_diff import compare_schema_snapshots


def _base() -> SchemaSnapshot:
    def col(table: str, name: str, ordinal: int) -> InspectedColumn:
        return InspectedColumn(
            schema_name="DEMIS_OWNER", table_name=table,
            ordinal_position=ordinal, column_name=name, data_type="VARCHAR2",
            character_maximum_length=32, numeric_precision=None, numeric_scale=None,
            is_nullable=True, default_value=None, column_comment="기본 주석",
        )
    return SchemaSnapshot(
        db_type="oracle",
        database_name="FREEPDB1",
        schema_name="DEMIS_OWNER",
        tables=[
            InspectedTable("DEMIS_OWNER", "TB_PARENT", "BASE TABLE", "부모"),
            InspectedTable("DEMIS_OWNER", "TB_CHILD", "BASE TABLE", "자식"),
        ],
        columns=[
            col("TB_PARENT", "ID", 1),
            col("TB_CHILD", "ID", 1),
            col("TB_CHILD", "PARENT_ID", 2),
            col("TB_CHILD", "AREA_ID", 3),
        ],
        primary_keys=[
            InspectedPrimaryKey("DEMIS_OWNER", "TB_PARENT", "PK_PARENT", "ID", 1),
            InspectedPrimaryKey("DEMIS_OWNER", "TB_CHILD", "PK_CHILD", "ID", 1),
        ],
        unique_constraints=[
            InspectedUniqueConstraint("DEMIS_OWNER", "TB_CHILD", "UQ_CHILD", "AREA_ID", 1),
            InspectedUniqueConstraint("DEMIS_OWNER", "TB_CHILD", "UQ_CHILD", "PARENT_ID", 2),
        ],
        foreign_keys=[
            InspectedForeignKey(
                "DEMIS_OWNER", "FK_CHILD_PARENT", "TB_CHILD",
                "DEMIS_OWNER", "TB_PARENT",
                columns=(
                    InspectedForeignKeyColumn(1, "PARENT_ID", "ID"),
                    InspectedForeignKeyColumn(2, "AREA_ID", "ID"),
                ),
            ),
        ],
        indexes=[
            InspectedIndex(
                "DEMIS_OWNER", "TB_CHILD", "IX_CHILD", False, "NORMAL", None,
                columns=(
                    InspectedIndexColumn(1, "PARENT_ID"),
                    InspectedIndexColumn(2, "AREA_ID"),
                ),
            ),
        ],
    )


def _diff(mutator=None):
    before = _base()
    after = deepcopy(before)
    if mutator:
        mutator(after)
    return compare_schema_snapshots(before, after)


def test_identical_snapshots_no_changes_with_explicit_baseline():
    diff = _diff()
    assert diff.identical
    assert diff.total_changes == 0
    assert diff.changes == ()
    assert diff.base_fingerprint == diff.target_fingerprint
    assert tuple(diff.counts) == (
        "TABLE", "COLUMN", "PRIMARY_KEY", "UNIQUE_CONSTRAINT", "FOREIGN_KEY", "INDEX"
    )
    assert all(x.total == 0 for x in diff.counts.values())


def test_order_permutation_does_not_change_fingerprint_or_package_fingerprint():
    base = _base()
    other = deepcopy(base)
    other.tables.reverse()
    other.columns.reverse()
    other.primary_keys.reverse()
    other.unique_constraints.reverse()
    other.foreign_keys[0] = replace(
        other.foreign_keys[0], columns=tuple(reversed(other.foreign_keys[0].columns))
    )
    other.indexes[0] = replace(
        other.indexes[0], columns=tuple(reversed(other.indexes[0].columns))
    )
    result = compare_schema_snapshots(base, other)
    assert result.identical
    assert result.base_fingerprint == result.target_fingerprint
    candidate = build_catalog_v2_candidate(
        other, source_name="oracle_demis_mock",
        generated_at=datetime(2026, 10, 14, tzinfo=timezone.utc),
    )
    assert validate_catalog_package_bytes(candidate).schema_fingerprint == result.target_fingerprint


def test_added_removed_changed_counts_and_only_safe_field_names():
    def modify(after):
        after.tables[0] = replace(after.tables[0], table_comment="변경된 주석")
        after.tables.append(InspectedTable("DEMIS_OWNER", "TB_NEW", "BASE TABLE", None))
        after.columns = [c for c in after.columns if c.column_name != "AREA_ID"]
        after.columns[0] = replace(after.columns[0], data_type="NUMBER")
        after.primary_keys.append(
            InspectedPrimaryKey("DEMIS_OWNER", "TB_NEW", "PK_NEW", "ID", 1)
        )
        after.unique_constraints = []
        after.indexes = []
    diff = _diff(modify)
    assert not diff.identical
    assert diff.counts["TABLE"].added == 1
    assert diff.counts["TABLE"].changed == 1
    assert diff.counts["COLUMN"].removed == 1
    assert diff.counts["COLUMN"].changed == 1
    assert diff.counts["PRIMARY_KEY"].added == 1
    assert diff.counts["UNIQUE_CONSTRAINT"].removed == 1
    assert diff.counts["INDEX"].removed == 1
    assert diff.total_changes == 7
    assert [(x.object_type, x.change_type, x.changed_fields) for x in diff.changes if x.change_type == "CHANGED"] == [
        ("TABLE", "CHANGED", ("table_comment",)),
        ("COLUMN", "CHANGED", ("data_type",)),
    ]
    assert all(isinstance(x.object_key, tuple) for x in diff.changes)
    assert all(not hasattr(x, "before") and not hasattr(x, "after") for x in diff.changes)


def test_composite_constraints_and_fk_index_ordinal_changes_are_detected():
    def modify(after):
        after.unique_constraints[0] = replace(
            after.unique_constraints[0], ordinal_position=2
        )
        after.unique_constraints[1] = replace(
            after.unique_constraints[1], ordinal_position=1
        )
        fk = after.foreign_keys[0]
        after.foreign_keys[0] = replace(
            fk, columns=(
                replace(fk.columns[0], target_column="ALT_ID"),
                fk.columns[1],
            )
        )
        ix = after.indexes[0]
        after.indexes[0] = replace(
            ix, columns=(InspectedIndexColumn(1, "AREA_ID"), InspectedIndexColumn(2, "PARENT_ID"))
        )
    diff = _diff(modify)
    assert diff.total_changes == 3
    assert {x.object_type: x.changed_fields for x in diff.changes} == {
        "UNIQUE_CONSTRAINT": ("columns",),
        "FOREIGN_KEY": ("columns",),
        "INDEX": ("columns",),
    }


def test_metadata_sql_definitions_and_defaults_never_appear_or_trigger_changes():
    def modify(after):
        after.columns[0] = replace(after.columns[0], default_value="SECRET-DEFAULT-SQL")
        after.indexes[0] = replace(after.indexes[0], index_definition="SECRET-INDEX-SQL")
    diff = _diff(modify)
    assert diff.identical
    assert diff.total_changes == 0
    assert "SECRET" not in str(diff)


@pytest.mark.parametrize("field,value", [
    ("db_type", "postgresql"),
    ("database_name", "OTHER_PDB"),
    ("schema_name", "OTHER_SCHEMA"),
])
def test_cross_target_diff_fail_closed(field, value):
    other = _base()
    setattr(other, field, value)
    with pytest.raises(ValueError, match="cross-target"):
        compare_schema_snapshots(_base(), other)


def test_missing_baseline_rejected_not_treated_as_unchanged():
    with pytest.raises(TypeError):
        compare_schema_snapshots(None, _base())


def test_duplicate_table_identity_rejected():
    target = _base()
    target.tables.append(target.tables[0])
    with pytest.raises(ValueError, match="duplicate SchemaSnapshot"):
        compare_schema_snapshots(_base(), target)


def test_duplicate_constraint_ordinal_rejected():
    target = _base()
    target.unique_constraints[1] = replace(target.unique_constraints[1], ordinal_position=1)
    with pytest.raises(ValueError, match="duplicate key constraint"):
        compare_schema_snapshots(_base(), target)


def test_duplicate_foreign_key_mapping_ordinal_rejected():
    target = _base()
    fk = target.foreign_keys[0]
    target.foreign_keys[0] = replace(
        fk, columns=(fk.columns[0], replace(fk.columns[1], ordinal_position=1))
    )
    with pytest.raises(ValueError, match="duplicate ordered"):
        compare_schema_snapshots(_base(), target)
