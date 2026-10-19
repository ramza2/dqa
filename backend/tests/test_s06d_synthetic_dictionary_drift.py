"""S-06-D: offline Oracle dictionary drift and provenance regression.

Uses the S-06-C in-memory Oracle Inspector fixture. No DB, credentials,
network, real DEMIS, activation, approval, or operational Catalog changes.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

import pytest

from app.adapters.schema_inspector.base import InspectedIndexColumn
from app.services.schema_snapshot_diff import compare_schema_snapshots
from tests.test_s06c_oracle_inspector_candidate_chain import _candidate, _inspect


def test_missing_dictionary_index_is_not_misreported_as_unchanged():
    """A visible index disappearing must change Diff and v2 fingerprints.

    The test cannot tell if Oracle metadata disappeared because of DDL or a
    changed dictionary grant. G1 requires an independently scoped DBA check.
    """
    baseline = _inspect()
    current = deepcopy(baseline)
    current.indexes.clear()

    diff = compare_schema_snapshots(baseline, current)
    assert not diff.identical
    assert diff.total_changes == 1
    assert [(change.object_type, change.change_type, change.object_key)
            for change in diff.changes] == [
        ("INDEX", "REMOVED", ("DEMIS_OWNER", "TB_VISIT", "IX_VISIT_PATIENT")),
    ]
    _, before = _candidate(baseline)
    _, after = _candidate(current)
    assert before.schema_fingerprint == diff.base_fingerprint
    assert after.schema_fingerprint == diff.target_fingerprint
    assert before.schema_fingerprint != after.schema_fingerprint
    assert after.package_readiness == "WARNING"
    assert not after.activation_eligible


def test_composite_fk_target_schema_and_column_mapping_change_are_visible():
    """Cross-schema references are metadata, not permission to query them."""
    baseline = _inspect()
    current = deepcopy(baseline)
    fk = current.foreign_keys[0]
    changed_columns = (
        fk.columns[0],
        replace(fk.columns[1], target_column="EXTERNAL_SITE_ID"),
    )
    current.foreign_keys[0] = replace(
        fk, target_schema="REFERENCE_OWNER", columns=changed_columns,
    )
    diff = compare_schema_snapshots(baseline, current)
    assert diff.total_changes == 1
    assert [(x.object_type, x.change_type, x.object_key, x.changed_fields)
            for x in diff.changes] == [
        (
            "FOREIGN_KEY", "CHANGED",
            ("DEMIS_OWNER", "TB_VISIT", "FK_VISIT_PATIENT"),
            ("columns", "target_schema"),
        ),
    ]
    _, validated = _candidate(current)
    assert validated.schema_fingerprint == diff.target_fingerprint
    assert validated.package_readiness == "WARNING"
    assert not validated.activation_eligible


def test_default_and_index_definition_are_ignored_and_not_exported():
    """Oracle SQL expressions must never enter the external v2 candidate."""
    baseline = _inspect()
    noisy = deepcopy(baseline)
    noisy.columns[0] = replace(
        noisy.columns[0], default_value="S06D_SENSITIVE_DEFAULT_EXPRESSION",
    )
    noisy.indexes[0] = replace(
        noisy.indexes[0], index_definition="S06D_SENSITIVE_INDEX_EXPRESSION",
    )
    diff = compare_schema_snapshots(baseline, noisy)
    assert diff.identical
    assert diff.total_changes == 0
    assert diff.base_fingerprint == diff.target_fingerprint

    archive_before, validation_before = _candidate(baseline)
    archive_noisy, validation_noisy = _candidate(noisy)
    assert archive_before == archive_noisy
    assert validation_before.schema_fingerprint == validation_noisy.schema_fingerprint
    assert b"S06D_SENSITIVE_" not in archive_noisy
    assert "S06D_SENSITIVE_" not in repr(diff)


def test_duplicate_index_ordinal_rejected_before_same_snapshot_claim():
    """Invalid compound-index structure is not a legitimate no-drift result."""
    baseline = _inspect()
    bad = deepcopy(baseline)
    index = bad.indexes[0]
    bad.indexes[0] = replace(
        index, columns=(
            InspectedIndexColumn(1, "PATIENT_ID"),
            InspectedIndexColumn(1, "SITE_ID"),
        ),
    )
    with pytest.raises(ValueError, match="duplicate ordered column ordinal"):
        compare_schema_snapshots(baseline, bad)
