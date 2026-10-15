"""U-02-A: compare original pinned legacy Oracle Inspector vs DQA, offline.

Opt in with DQA_U02_LEGACY_ROOT=path-to-detached-legacy-checkout.
Each original implementation is imported in a separate Python interpreter.
No test import shadows DQA's production "app" package.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


LEGACY_SHA = "c9b88f6f6d14dc2598765efbf6bb41b4771f9b25"
BACKEND = Path(__file__).resolve().parents[1]
RUNNER = Path(__file__).with_name("u02_oracle_parity_runner.py")
LEGACY_ROOT_ENV = "DQA_U02_LEGACY_ROOT"


@pytest.fixture(scope="module")
def legacy_backend() -> Path:
    raw = os.environ.get(LEGACY_ROOT_ENV)
    if not raw:
        pytest.skip("U-02 parity opt-in: DQA_U02_LEGACY_ROOT not supplied")
    repo = Path(raw).resolve(strict=True)
    actual = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=10,
    ).stdout.strip()
    assert actual == LEGACY_SHA, "legacy source must be exactly pinned baseline"
    for relative in ("backend/app/analyzers/oracle.py", "backend/app/analyzers/base.py"):
        source_path = repo / relative
        assert source_path.is_file()
        expected_blob = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", f"HEAD:{relative}"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        actual_blob = subprocess.run(
            ["git", "-C", str(repo), "hash-object", str(source_path)],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        assert actual_blob == expected_blob, "legacy tracked source modified"
    return repo / "backend"


def _run(mode: str, kind: str, legacy_backend: Path) -> dict:
    selected = legacy_backend if mode == "legacy" else BACKEND
    env = os.environ.copy()
    # Avoid silently importing the other project's app package.
    env["PYTHONPATH"] = str(selected)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable, "-B", str(RUNNER), mode, kind,
    ]
    output = subprocess.run(
        command, cwd=str(selected), env=env, text=True,
        capture_output=True, check=True, timeout=20,
    )
    return json.loads(output.stdout)


@pytest.mark.parametrize("case", ["rich", "empty", "changed_comment"])
def test_legacy_and_dqa_oracle_snapshot_parity(case, legacy_backend):
    legacy = _run("legacy", case, legacy_backend)
    dqa = _run("dqa", case, legacy_backend)
    # Compare all nested physical DTO fields, not hashes: hash algorithms and
    # package readiness are intentionally outside this Inspector comparison.
    assert dqa["snapshot"] == legacy["snapshot"]
    assert dqa["snapshot"]["db_type"] == "oracle"
    assert dqa["snapshot"]["database_name"] == "FREEPDB1"
    assert dqa["snapshot"]["schema_name"] == "DEMIS_OWNER"
    assert legacy["inspect_queries"] == dqa["inspect_queries"] == 6


def test_known_security_and_schema_listing_differences(legacy_backend):
    legacy = _run("legacy", "rich", legacy_backend)
    dqa = _run("dqa", "rich", legacy_backend)

    # DQA hardens the original Oracle reads by explicitly starting a
    # read-only transaction; the historical implementation does not.
    assert legacy["inspect_readonly_starts"] == 0
    assert dqa["inspect_readonly_starts"] == 1
    assert legacy["total_readonly_starts"] == 0
    assert dqa["total_readonly_starts"] == 2

    # Old list_schemas consumes mapping rows *after* its connection closed.
    # This synthetic closed-cursor check documents the DQA correction rather
    # than misreporting the two APIs as semantically identical.
    assert legacy["schema_listing"] == {"status": "CURSOR_CLOSED"}
    assert dqa["schema_listing"] == {
        "status": "OK", "schemas": ["DEMIS_OWNER", "APP_OWNER"],
    }


def test_comparison_fixture_detects_real_metadata_change(legacy_backend):
    old = _run("dqa", "rich", legacy_backend)["snapshot"]
    changed = _run("dqa", "changed_comment", legacy_backend)["snapshot"]
    assert old != changed, "parity harness must detect a changed fixture"
    assert old["tables"][1]["table_comment"] != changed["tables"][1]["table_comment"]
    assert old["columns"][0]["column_comment"] != changed["columns"][0]["column_comment"]
    assert old["foreign_keys"] == changed["foreign_keys"]
