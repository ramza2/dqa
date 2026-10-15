"""U-02-B offline fingerprint-contract differences, pinned legacy vs DQA.

Explicit opt-in: DQA_U02_LEGACY_ROOT must point to a disposable checkout at
c9b88f6. Pinned original writer/fingerprint/Oracle collector files are checked
against Git blob IDs before executing. No DB/Oracle/HTTP traffic.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


LEGACY_SHA = "c9b88f6d6d14dc2598765efbf6bb41b4771f9b25"
BACKEND = Path(__file__).resolve().parents[1]
RUNNER = Path(__file__).with_name("u02_package_contract_runner.py")


@pytest.fixture(scope="module")
def legacy_backend() -> Path:
    raw = os.environ.get("DQA_U02_LEGACY_ROOT")
    if not raw:
        pytest.skip("U-02-B requires explicit DQA_U02_LEGACY_ROOT")
    root = Path(raw).resolve(strict=True)
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True,
            text=True, check=True, timeout=10,
        ).stdout.strip()

    assert git("rev-parse", "HEAD") == LEGACY_SHA
    for relative in (
        "backend/app/analyzers/oracle.py",
        "backend/app/analyzers/base.py",
        "backend/app/services/catalog_writer.py",
        "backend/app/services/fingerprint.py",
    ):
        file_path = root / relative
        assert file_path.is_file()
        assert git("hash-object", str(file_path)) == git("rev-parse", f"HEAD:{relative}")
    return root / "backend"


def _run(mode: str, variation: str, legacy_backend: Path) -> dict:
    selected = legacy_backend if mode == "legacy" else BACKEND
    env = os.environ.copy()
    env["PYTHONPATH"] = str(selected)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", str(RUNNER), mode, variation],
        cwd=str(selected), env=env, capture_output=True,
        text=True, check=True, timeout=25,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize("variation", [
    "rich", "comment", "length", "precision", "default", "index_sql",
])
def test_real_legacy_fingerprint_and_dqa_warning_candidate(variation, legacy_backend):
    legacy = _run("legacy", variation, legacy_backend)
    dqa = _run("dqa", variation, legacy_backend)
    assert isinstance(legacy["fingerprint"], str) and len(legacy["fingerprint"]) == 64
    assert isinstance(dqa["fingerprint"], str) and len(dqa["fingerprint"]) == 64
    # Both are SHA-256, but are over DIFFERENT normalized field sets.
    assert dqa["fingerprint"] != legacy["fingerprint"]
    assert dqa["format"] == "demis-catalog-package"
    assert dqa["version"] == "2.0"
    assert dqa["readiness"] == "WARNING"
    assert dqa["activation_eligible"] is False
    assert dqa["has_valid_file_digests"] is True
    assert dqa["has_consistent_fingerprints"] is True
    assert dqa["no_sensitive_values"] is True
    assert dqa["managed_file_count"] == 11
    assert dqa["file_paths"] == dqa["required_paths"]


@pytest.mark.parametrize("mode", ["legacy", "dqa"])
def test_comment_mutation_changes_both_fingerprints(mode, legacy_backend):
    original = _run(mode, "rich", legacy_backend)["fingerprint"]
    changed = _run(mode, "comment", legacy_backend)["fingerprint"]
    assert original != changed


@pytest.mark.parametrize("variation", ["length", "precision"])
def test_legacy_omits_column_shape_fields_while_dqa_tracks_them(
    variation, legacy_backend,
):
    original_legacy = _run("legacy", "rich", legacy_backend)["fingerprint"]
    changed_legacy = _run("legacy", variation, legacy_backend)["fingerprint"]
    original_dqa = _run("dqa", "rich", legacy_backend)["fingerprint"]
    changed_dqa = _run("dqa", variation, legacy_backend)["fingerprint"]
    assert original_legacy == changed_legacy
    assert original_dqa != changed_dqa


def test_sql_default_not_exported_and_legacy_hash_includes_it(legacy_backend):
    legacy_original = _run("legacy", "rich", legacy_backend)["fingerprint"]
    legacy_modified = _run("legacy", "default", legacy_backend)["fingerprint"]
    dqa_original = _run("dqa", "rich", legacy_backend)
    dqa_modified = _run("dqa", "default", legacy_backend)
    assert legacy_original != legacy_modified
    assert dqa_original["fingerprint"] == dqa_modified["fingerprint"]
    assert dqa_modified["no_sensitive_values"] is True
    assert dqa_modified["physical"]["columns"][0]["default_value"] is None


def test_index_sql_is_omitted_in_both_fingerprints_and_dqa_export(legacy_backend):
    for mode in ("legacy", "dqa"):
        assert _run(mode, "rich", legacy_backend)["fingerprint"] == (
            _run(mode, "index_sql", legacy_backend)["fingerprint"]
        )
    actual = _run("dqa", "index_sql", legacy_backend)
    assert actual["no_sensitive_values"] is True
    assert actual["physical"]["indexes"][0]["columns"] == [
        "PATIENT_ID", "SITE_ID",
    ]


def test_dqa_v2_core_shapes_and_composite_mapping(legacy_backend):
    dqa = _run("dqa", "rich", legacy_backend)
    assert dqa["counts"] == {
        "tables": 2, "columns": 3, "relations": 1, "indexes": 1,
        "categories": 0, "category_assignments": 0,
    }
    cols = dqa["physical"]["columns"]
    assert cols[0]["data_type"] == "VARCHAR2"
    assert cols[0]["character_maximum_length"] == 30
    assert cols[1]["numeric_precision"] == 5
    assert [item["column_name"] for item in cols] == [
        "PATIENT_ID", "SITE_ID", "PATIENT_ID",
    ]
    assert dqa["physical"]["relations"][0]["column_mapping"] == [
        {"ordinal_position": 1, "source_column": "PATIENT_ID", "target_column": "PATIENT_ID"},
        {"ordinal_position": 2, "source_column": "SITE_ID", "target_column": "SITE_ID"},
    ]
    assert dqa["physical"]["indexes"][0]["columns"] == ["PATIENT_ID", "SITE_ID"]
