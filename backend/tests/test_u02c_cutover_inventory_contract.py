"""U-02-C-1 static legacy Catalog data cutover inventory contract.

No DB connection, no migration or DQA runtime modifications.
Opt-in pinned Legacy repository SHA+Git-blob comparison validates the source
ORM table universe. Other tests validate the DQA target models and policy.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
from collections import Counter
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "docs/u02-c-legacy-cutover-inventory.json"
DQA_MODELS = REPO / "backend/app/models"
EXPECTED_LEGACY_SHA = "c9b88f6f6d14dc2598765efbf6bb41b4771f9b25"
ALLOWED_DISPOSITIONS = {
    "package_physical", "package_semantic", "archive_lineage",
    "archive_untrusted", "rebuild", "reconfigure",
}
EXPECTED_COUNTS = {
    "package_physical": 8, "package_semantic": 2, "archive_lineage": 2,
    "archive_untrusted": 1, "rebuild": 3, "reconfigure": 1,
}


def _load() -> dict:
    return json.loads(MANIFEST.read_text("utf-8"))


def _model_classes(path: Path) -> dict[str, str]:
    """Return class name -> table name from source AST, without importing code."""
    tree = ast.parse(path.read_text("utf-8"), filename=str(path))
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == "__tablename__"
                       for target in stmt.targets):
                continue
            if isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
                found[node.name] = stmt.value.value
    return found


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, timeout=10, check=True,
    ).stdout.strip()


def test_manifest_has_complete_unique_dispositions():
    m = _load()
    assert m["scope"] == "source-code-only-plan; no actual Legacy DB rows read"
    assert m["cutover_status"] == "NOT_APPROVED"
    assert m["source_sha"] == EXPECTED_LEGACY_SHA
    records = m["legacy_orm_inventory"]
    assert len(records) == 17
    assert len({x["legacy_table"] for x in records}) == len(records)
    assert len({x["legacy_model"] for x in records}) == len(records)
    assert Counter(x["disposition"] for x in records) == EXPECTED_COUNTS
    for row in records:
        assert row["disposition"] in ALLOWED_DISPOSITIONS
        assert row["legacy_model_file"].startswith("backend/app/models/")
        assert row["destination"].strip()
        assert row["acceptance"].strip()


def test_all_explicit_dqa_target_tables_exist():
    rows = _load()["legacy_orm_inventory"]
    all_models = {}
    for py in DQA_MODELS.glob("*.py"):
        all_models.update(_model_classes(py))
    target_tables = set(all_models.values())
    for item in rows:
        if item["target_table"] is not None:
            assert item["target_table"] in target_tables, item["legacy_model"]


def test_critical_no_copy_no_auto_ready_invariants():
    rows = {r["legacy_table"]: r for r in _load()["legacy_orm_inventory"]}
    assert rows["catalog_source"]["disposition"] == "reconfigure"
    assert rows["catalog_source"]["target_table"] == "connection_profiles"
    assert rows["catalog_analysis_run"]["disposition"] == "archive_lineage"
    assert rows["catalog_analysis_snapshot"]["disposition"] == "archive_lineage"
    assert rows["catalog_preflight_result"]["disposition"] == "archive_untrusted"
    assert rows["catalog_preflight_result"]["target_table"] is None
    assert {rows[name]["disposition"] for name in (
        "catalog_search_document", "catalog_embedding_run", "catalog_embedding"
    )} == {"rebuild"}
    assert rows["catalog_embedding"]["target_table"] == "data_discovery_embeddings"
    assert rows["catalog_table_category"]["disposition"] == "package_semantic"
    artifacts = {x["id"]: x for x in _load()["non_table_artifacts"]}
    assert artifacts["legacy-live-target-secrets"]["decision"] == "never_migrate"
    assert artifacts["legacy-fingerprint"]["decision"] == "recompute_and_crosswalk"


def test_pinned_legacy_model_coverage_and_blob_integrity():
    root_path = os.environ.get("DQA_U02_LEGACY_ROOT")
    if not root_path:
        pytest.skip("Set DQA_U02_LEGACY_ROOT for pinned original ORM coverage")
    root = Path(root_path).resolve(strict=True)
    assert _git(root, "rev-parse", "HEAD") == EXPECTED_LEGACY_SHA
    rows = _load()["legacy_orm_inventory"]
    paths = sorted({x["legacy_model_file"] for x in rows})
    observed = {}
    for rel in paths:
        path = root / rel
        assert path.is_file()
        assert _git(root, "hash-object", str(path)) == _git(
            root, "rev-parse", f"HEAD:{rel}",
        )
        for model, table in _model_classes(path).items():
            assert table not in observed
            observed[table] = (model, rel)
    expected = {
        row["legacy_table"]: (row["legacy_model"], row["legacy_model_file"])
        for row in rows
    }
    assert observed == expected
