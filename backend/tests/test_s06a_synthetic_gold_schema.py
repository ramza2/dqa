"""S-06-A offline schema Gold Set (synthetic metadata only; no DB/Oracle).

This extends, rather than duplicates, test_schema_snapshot_diff.py by fixing
the expected CHANGED/ADDED/REMOVED field-level outcomes for mixed changes.
It makes no claim of matching real DEMIS metadata or Legacy's raw fingerprint.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone

from app.adapters.schema_inspector.base import (
    InspectedIndexColumn,
    InspectedPrimaryKey,
    InspectedUniqueConstraint,
)
from app.services.catalog_package_validation import validate_catalog_package_bytes
from app.services.schema_catalog_candidate import build_catalog_v2_candidate
from app.services.schema_snapshot_diff import compare_schema_snapshots
from tests.test_schema_snapshot_diff import _base


def _gold_changes():
    previous = _base()
    current = deepcopy(previous)
    # Composite key order, FK mapping/target schema, index ordering and
    # null→empty comment semantics are intentionally represented distinctly.
    current.tables[0] = replace(current.tables[0], table_comment=None)
    current.tables[1] = replace(current.tables[1], table_comment="")
    current.columns[0] = replace(current.columns[0], column_comment="")
    current.primary_keys.append(
        InspectedPrimaryKey("DEMIS_OWNER", "TB_PARENT", "PK_PARENT", "AREA_ID", 2),
    )
    current.unique_constraints = [
        InspectedUniqueConstraint("DEMIS_OWNER", "TB_CHILD", "UQ_CHILD", "PARENT_ID", 1),
        InspectedUniqueConstraint("DEMIS_OWNER", "TB_CHILD", "UQ_CHILD", "AREA_ID", 2),
    ]
    old_fk = current.foreign_keys[0]
    current.foreign_keys[0] = replace(
        old_fk,
        target_schema="EXTERNAL_OWNER",
        columns=(
            replace(old_fk.columns[0], target_column="EXT_ID"),
            old_fk.columns[1],
        ),
    )
    current.indexes[0] = replace(
        current.indexes[0],
        columns=(
            InspectedIndexColumn(1, "AREA_ID"),
            InspectedIndexColumn(2, "PARENT_ID"),
        ),
    )
    return previous, current


GOLD_CHANGED = {
    ("TABLE", ("DEMIS_OWNER", "TB_PARENT")): ("table_comment",),
    ("TABLE", ("DEMIS_OWNER", "TB_CHILD")): ("table_comment",),
    ("COLUMN", ("DEMIS_OWNER", "TB_PARENT", "ID")): ("column_comment",),
    ("PRIMARY_KEY", ("DEMIS_OWNER", "TB_PARENT", "PK_PARENT")): ("columns",),
    ("UNIQUE_CONSTRAINT", ("DEMIS_OWNER", "TB_CHILD", "UQ_CHILD")): ("columns",),
    ("FOREIGN_KEY", ("DEMIS_OWNER", "TB_CHILD", "FK_CHILD_PARENT")): (
        "columns", "target_schema",
    ),
    ("INDEX", ("DEMIS_OWNER", "TB_CHILD", "IX_CHILD")): ("columns",),
}


def test_gold_composite_fk_uk_index_and_comment_expected_field_diff():
    base, changed = _gold_changes()
    result = compare_schema_snapshots(base, changed)
    actual = {
        (item.object_type, item.object_key): item.changed_fields
        for item in result.changes if item.change_type == "CHANGED"
    }
    assert actual == GOLD_CHANGED
    assert result.total_changes == len(GOLD_CHANGED)
    assert result.counts["FOREIGN_KEY"].changed == 1
    assert result.counts["INDEX"].changed == 1
    assert result.counts["UNIQUE_CONSTRAINT"].changed == 1
    assert all(x.change_type == "CHANGED" for x in result.changes)
    assert not any(hasattr(x, "before") or hasattr(x, "after") for x in result.changes)
    assert "EXTERNAL_OWNER" not in str(result.changes)
    assert "EXT_ID" not in str(result.changes)


def test_gold_physical_fingerprint_and_v2_warning_candidate_agree():
    old, changed = _gold_changes()
    diff = compare_schema_snapshots(old, changed)
    candidate = build_catalog_v2_candidate(
        changed,
        source_name="s06a_schema_gold",
        generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )
    validation = validate_catalog_package_bytes(candidate)
    assert validation.schema_fingerprint == diff.target_fingerprint
    assert validation.schema_fingerprint != diff.base_fingerprint
    assert validation.package_readiness == "WARNING"
    assert validation.activation_eligible is False


def test_gold_capture_order_permutation_is_stable_but_change_is_not():
    old, changed = _gold_changes()
    shuffled = deepcopy(changed)
    for name in (
        "tables", "columns", "primary_keys", "unique_constraints",
        "foreign_keys", "indexes",
    ):
        getattr(shuffled, name).reverse()
    shuffled.foreign_keys[0] = replace(
        shuffled.foreign_keys[0],
        columns=tuple(reversed(shuffled.foreign_keys[0].columns)),
    )
    shuffled.indexes[0] = replace(
        shuffled.indexes[0],
        columns=tuple(reversed(shuffled.indexes[0].columns)),
    )
    reordered = compare_schema_snapshots(changed, shuffled)
    assert reordered.identical and reordered.total_changes == 0
    assert reordered.base_fingerprint == reordered.target_fingerprint
    assert compare_schema_snapshots(old, shuffled).target_fingerprint == reordered.target_fingerprint


def test_gold_excluded_default_sql_and_index_definition_never_become_diff_evidence():
    before, after = _gold_changes()
    noisy = deepcopy(after)
    noisy.columns[0] = replace(noisy.columns[0], default_value="SYNTHETIC_SECRET_DEFAULT")
    noisy.indexes[0] = replace(
        noisy.indexes[0], index_definition="SYNTHETIC_SECRET_INDEX_DEFINITION",
    )
    result = compare_schema_snapshots(after, noisy)
    assert result.identical
    assert result.total_changes == 0
    assert "SYNTHETIC_SECRET" not in repr(result)
