"""U-02-B-2: pinned real Legacy finalizer ZIP -> DQA's actual v2 validator.

No Oracle, PostgreSQL, production Legacy, import or activation operations.
Legacy real writer/finalizer use an isolated synthetic Session double; their
report-rendering and preflight lookup dependencies are test doubles.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from app.adapters.catalog.errors import CatalogPackageErrorCode, CatalogPackageValidationError
from app.adapters.catalog.limits import REQUIRED_RUNTIME_JSON_FILES
from app.services.catalog_package_validation import validate_catalog_package_bytes


LEGACY_SHA = "c9b88f6f6d14dc2598765efbf6bb41b4771f9b25"
RUNNER = Path(__file__).with_name("u02b2_legacy_final_zip_runner.py")
SENTINELS = (
    b"U02B2_PRIVATE_HOST_SENTINEL",
    b"U02B2_PRIVATE_USER_SENTINEL",
    b"U02B2_PRIVATE_SECRET_SENTINEL",
)
PINNED_FILES = (
    "backend/app/services/catalog_package_finalizer.py",
    "backend/app/services/catalog_package.py",
    "backend/app/models/catalog.py",
    "backend/app/models/catalog_category.py",
    "backend/app/models/catalog_history.py",
)


def _git(root: Path, *params: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *params],
        text=True, capture_output=True, check=True, timeout=10,
    ).stdout.strip()


@pytest.fixture(scope="module")
def legacy_backend() -> Path:
    raw = os.environ.get("DQA_U02_LEGACY_ROOT")
    if not raw:
        pytest.skip("U-02-B-2 requires explicit pinned DQA_U02_LEGACY_ROOT")
    root = Path(raw).resolve(strict=True)
    assert _git(root, "rev-parse", "HEAD") == LEGACY_SHA
    for relative in PINNED_FILES:
        assert (root / relative).is_file()
        assert _git(root, "hash-object", str(root / relative)) == _git(
            root, "rev-parse", f"HEAD:{relative}",
        )
    return root / "backend"


def _build_legacy_zip(legacy_backend: Path, status: str) -> tuple[bytes, dict]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(legacy_backend)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-B", str(RUNNER), status],
        cwd=str(legacy_backend), env=env, text=True,
        capture_output=True, check=True, timeout=30,
    )
    output = json.loads(result.stdout)
    archive = base64.b64decode(output["archive_b64"], validate=True)
    return archive, output


def _files(archive: bytes) -> dict[str, bytes]:
    prefix = "demis_catalog_package/"
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        names = zf.namelist()
        assert len(names) == len(set(names))
        assert all(name.startswith(prefix) for name in names)
        return {name[len(prefix):]: zf.read(name) for name in names}


@pytest.fixture(scope="module")
def warning_zip(legacy_backend: Path) -> tuple[bytes, dict, dict]:
    archive, output = _build_legacy_zip(legacy_backend, "WARNING")
    return archive, output, _files(archive)


def test_real_legacy_v2_finalizer_zip_validates_as_warning(warning_zip):
    archive, output, files = warning_zip
    checked = validate_catalog_package_bytes(archive)
    manifest = json.loads(files["manifest.json"])
    assert output["filename"].endswith("_v2.zip")
    assert output["manifest_readiness"] == "WARNING"
    assert checked.package_format == "demis-catalog-package"
    assert checked.package_version == "2.0"
    assert checked.package_readiness == "WARNING"
    assert checked.activation_eligible is False
    assert checked.source.source_name == "oracle_demis_mock"
    assert checked.source.default_schema == "DEMIS_OWNER"
    assert checked.schema_fingerprint == manifest["schema_fingerprint"]
    assert checked.manifest_sha256 == hashlib.sha256(files["manifest.json"]).hexdigest()
    assert set(REQUIRED_RUNTIME_JSON_FILES).issubset(files)
    assert checked.files_validated == len(files) - 1
    assert checked.files_validated > len(REQUIRED_RUNTIME_JSON_FILES)
    assert set(x["path"] for x in manifest["files"]) == set(files) - {"manifest.json"}
    for item in manifest["files"]:
        data = files[item["path"]]
        assert len(data) == item["bytes"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
    assert "PACKAGE_README.md" in files
    assert "diff/latest_summary.md" in files
    assert any(name.startswith("reports/") and name.endswith(".docx") for name in files)
    assert all(secret not in archive for secret in SENTINELS)
    assert all(secret not in data for data in files.values() for secret in SENTINELS)


def test_legacy_keys_categories_and_composite_mapping_survive(warning_zip):
    archive, _, files = warning_zip
    checked = validate_catalog_package_bytes(archive)
    assert checked.counts == {
        "tables": 2, "columns": 5, "relations": 1, "indexes": 1,
        "categories": 1, "category_assignments": 1,
    }
    tables = json.loads(files["tables.json"])["tables"]
    patient = next(t for t in tables if t["table_name"] == "PATIENT_REF")
    assert patient["key_constraints"] == [{
        "constraint_name": "PK_PATIENT", "constraint_type": "PRIMARY_KEY",
        "columns": ["PATIENT_ID", "SITE_ID"],
    }]
    category_doc = json.loads(files["categories.json"])
    assert category_doc["categories"][0]["category_key"] == "TEST_ONLY"
    assert category_doc["table_assignments"] == [{
        "table_key": "DEMIS_OWNER.VISIT_REF", "category_key": "TEST_ONLY",
        "is_primary": True, "assignment_source": "MANUAL",
        "confidence": 1.0, "note": "fixture only",
    }]
    relations = checked.parsed_documents["relations.json"]["relations"]
    assert relations[0]["column_mapping"] == [
        {"ordinal_position": 1, "source_column": "PATIENT_ID", "target_column": "PATIENT_ID"},
        {"ordinal_position": 2, "source_column": "SITE_ID", "target_column": "SITE_ID"},
    ]
    assert checked.parsed_documents["indexes.json"]["indexes"][0]["columns"] == [
        "PATIENT_ID", "SITE_ID",
    ]
    assert checked.parsed_documents["validation/preflight.json"]["connection"]["username_exported"] is False
    assert checked.parsed_documents["diff/latest.json"]["available"] is False


def test_legacy_zip_tamper_detected(warning_zip):
    _, _, files = warning_zip
    tampered = dict(files)
    tampered["categories.json"] = tampered["categories.json"].replace(
        b'"TEST_ONLY"', b'"ALTERED__"', 1,
    )
    assert tampered["categories.json"] != files["categories.json"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in tampered.items():
            zf.writestr(f"demis_catalog_package/{name}", content)
    with pytest.raises(CatalogPackageValidationError) as error:
        validate_catalog_package_bytes(buffer.getvalue())
    assert error.value.code == CatalogPackageErrorCode.CHECKSUM_MISMATCH
    assert error.value.path == "categories.json"


def test_legacy_ready_validates_structurally_but_is_not_dba_evidence(legacy_backend):
    archive, output = _build_legacy_zip(legacy_backend, "READY")
    checked = validate_catalog_package_bytes(archive)
    assert output["manifest_readiness"] == "READY"
    assert checked.package_readiness == "READY"
    # WARNING: DQA currently derives activation_eligible from manifest READY.
    # This is NOT signed site approval or independent DBA preflight evidence.
    # This test must never call catalog import/activation or any production APIs.
    assert checked.activation_eligible is True
