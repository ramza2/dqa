"""U-02-C-2: aggregate-only Legacy Source/Run inventory and safe crosswalk tests.

Offline unit tests need no DB. Optional generated evidence is from the
disposable U-02-C-2 PostgreSQL Compose integration. No DQA import/activation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from u02c2_inventory_core import InventoryRejected, TABLES, validate_run_links


def test_valid_source_run_crosswalk_retains_only_ephemeral_aliases():
    evidence = validate_run_links(
        [101, 202],
        [(12, 101, "SUCCESS"), (13, 101, "FAILED"), (55, 202, "SUCCESS")],
        [(301, 101, 12), (302, 202, 55)],
    )
    assert evidence[101]["run_status_counts"] == {
        "SUCCESS": 1, "FAILED": 1, "OTHER": 0,
    }
    assert evidence[101]["run_evidence"] == [
        {
            "run_alias": "RUN_0001", "status_class": "SUCCESS",
            "snapshot_present": True, "dqa_snapshot_revision_id": None,
            "dqa_import_revision_id": None,
        },
        {
            "run_alias": "RUN_0002", "status_class": "FAILED",
            "snapshot_present": False, "dqa_snapshot_revision_id": None,
            "dqa_import_revision_id": None,
        },
    ]


@pytest.mark.parametrize("runs,snapshots,error", [
    ([(10, 1, "SUCCESS"), (10, 1, "SUCCESS")], [], "RUN_SOURCE_OR_DUPLICATE"),
    ([(10, 2, "SUCCESS")], [], "RUN_SOURCE_OR_DUPLICATE"),
    ([(10, 1, "SUCCESS")], [(20, 2, 10)], "SNAPSHOT_LINK_INVALID"),
    ([(10, 1, "SUCCESS")], [(20, 1, 999)], "SNAPSHOT_LINK_INVALID"),
    ([(10, 1, "SUCCESS")], [(20, 1, 10), (21, 1, 10)],
     "MULTIPLE_SNAPSHOTS_FOR_RUN"),
    ([(10, 1, "FAILED")], [(20, 1, 10)], "SNAPSHOT_RUN_NOT_SUCCESS"),
    ([(10, 1, "SUCCESS")], [(20, 1, 10), (20, 1, 10)], "SNAPSHOT_LINK_INVALID"),
])
def test_mapping_rejects_corrupt_links(runs, snapshots, error):
    with pytest.raises(InventoryRejected, match=f"^{error}$"):
        validate_run_links([1], runs, snapshots)


def test_missing_snapshot_never_claims_import_or_authority():
    evidence = validate_run_links([1], [(2, 1, "RUNNING"), (3, 1, "SUCCESS")], [])
    assert evidence[1]["run_status_counts"] == {
        "SUCCESS": 1, "FAILED": 0, "OTHER": 1,
    }
    assert all(not row["snapshot_present"] for row in evidence[1]["run_evidence"])
    assert all(row["dqa_import_revision_id"] is None for row in
               evidence[1]["run_evidence"])


def test_core_has_exactly_17_allowlisted_legacy_inventory_tables():
    inventory_path = Path(__file__).resolve().parents[2] / "docs/u02-c-legacy-cutover-inventory.json"
    source = json.loads(inventory_path.read_text("utf-8"))
    assert len(TABLES) == 17
    assert set(TABLES) == {x["legacy_table"] for x in source["legacy_orm_inventory"]}


@pytest.fixture(scope="module")
def pg_evidence():
    directory = os.environ.get("DQA_U02C2_ARTIFACT_DIR")
    if not directory:
        pytest.skip("isolated PG evidence requires DQA_U02C2_ARTIFACT_DIR")
    return json.loads((Path(directory).resolve(strict=True) / "u02c2_inventory.json").read_text("utf-8"))


def test_real_isolated_pg_counts_and_unresolved_dqa_mapping(pg_evidence):
    assert pg_evidence["evidence_kind"] == "SYNTHETIC_ISOLATED_LEGACY_PG"
    assert pg_evidence["cutover_allowed"] is False
    assert pg_evidence["role"] == "AGGREGATE_EVIDENCE_ONLY"
    assert pg_evidence["alias_policy"] == "EPHEMERAL_POSITIONAL_NOT_DURABLE_CROSSWALK"
    assert pg_evidence["table_count"] == len(TABLES) == 17
    sources = pg_evidence["sources"]
    assert len(sources) == 2
    assert [s["source_alias"] for s in sources] == ["SRC_001", "SRC_002"]
    for src in sources:
        assert set(src["table_counts"]) == set(TABLES)
        assert src["table_counts"]["catalog_source"] == 1
        assert src["table_counts"]["catalog_analysis_run"] == 2
        assert src["table_counts"]["catalog_analysis_snapshot"] == 2
        assert src["run_status_counts"] == {"SUCCESS": 2, "FAILED": 0, "OTHER": 0}
        assert all(run["snapshot_present"] and run["dqa_import_revision_id"] is None
                   for run in src["run_evidence"])
        assert src["source_to_dqa"] == {
            "dqa_source_name": None, "dqa_catalog_import_revision_id": None,
            "status": "UNRESOLVED_PENDING_APPROVAL",
        }
    first, second = sources
    for table in ("catalog_category", "catalog_table_category",
                  "catalog_search_document", "catalog_embedding_run", "catalog_embedding"):
        assert first["table_counts"][table] == 1
        assert second["table_counts"][table] == 0
    serialized = json.dumps(pg_evidence)
    for forbidden in ("SECRET_DB_HOST", "SECRET_DB_USER", "SECRET_CIPHERTEXT",
                      "DO_NOT_EXPORT", "u02b2b_user", "u02c2_reader",
                      "oracle_demis_mock", "final_package_",
                      "SYNTHETIC ONLY", "u02b2b_fixture_only_never_prod"):
        assert forbidden not in serialized
