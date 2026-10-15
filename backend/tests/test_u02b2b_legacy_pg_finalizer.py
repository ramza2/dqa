"""U-02-B-2-B: isolated original Legacy PostgreSQL final ZIP -> DQA v2 validator.

The ZIPs must be created by scripts/u02b2b/run.sh from a disposable,
unpublished PostgreSQL container. This test does not connect to any DB.
No import, activation or external DEMIS operations.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from app.adapters.catalog.errors import CatalogPackageErrorCode, CatalogPackageValidationError
from app.services.catalog_package_validation import validate_catalog_package_bytes


STATUSES = ("READY", "WARNING", "BLOCKED")
PREFIX = "demis_catalog_package/"
SENTINELS = (
    b"SECRET_DB_HOST", b"SECRET_DB_USER",
    b"SECRET_CIPHERTEXT", b"DO_NOT_EXPORT",
)


@pytest.fixture(scope="module")
def output_directory() -> Path:
    value = os.environ.get("DQA_U02B2B_ARTIFACT_DIR")
    if not value:
        pytest.skip("explicit U-02-B-2-B isolated fixture output is required")
    directory = Path(value).resolve(strict=True)
    assert directory.is_dir()
    summary = json.loads((directory / "generation_summary.json").read_text("utf-8"))
    assert summary["fixture"] == "u02b2b-disposable-legacy-pg"
    assert {x["status"] for x in summary["results"]} == set(STATUSES)
    assert all(x["report_verified_as_docx"] and x["diff_verified"] for x in summary["results"])
    return directory


def package_files(path: Path) -> dict[str, bytes]:
    payload = path.read_bytes()
    assert payload
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert all(p.startswith(PREFIX) for p in names)
        return {name[len(PREFIX):]: archive.read(name) for name in names}


@pytest.mark.parametrize("status,eligible", [
    ("READY", True), ("WARNING", False), ("BLOCKED", False),
])
def test_real_postgres_finalizer_archive_validates(status, eligible, output_directory):
    content = (output_directory / f"final_{status}.zip").read_bytes()
    validated = validate_catalog_package_bytes(content)
    files = package_files(output_directory / f"final_{status}.zip")
    manifest = json.loads(files["manifest.json"])
    assert manifest["package_version"] == validated.package_version == "2.0"
    assert manifest["package_format"] == validated.package_format == "demis-catalog-package"
    assert validated.package_readiness == status
    assert validated.activation_eligible is eligible
    assert validated.source.default_schema == "DEMIS_OWNER"
    assert manifest["schema_fingerprint"] == validated.schema_fingerprint
    assert manifest["artifacts"]["preflight"]["status"] == status
    assert validated.files_validated == len(manifest["files"])
    assert hashlib.sha256(files["manifest.json"]).hexdigest() == validated.manifest_sha256
    assert validated.counts["tables"] == 1
    assert validated.counts["columns"] == 1
    assert validated.counts["categories"] == 1
    assert validated.counts["category_assignments"] == 1
    for item in manifest["files"]:
        data = files[item["path"]]
        assert len(data) == item["bytes"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"]


def test_persisted_preflight_two_run_diff_category_and_real_docx(output_directory):
    files = package_files(output_directory / "final_READY.zip")
    manifest = json.loads(files["manifest.json"])
    assert manifest["artifacts"]["schema_snapshot"]["available"] is True
    assert manifest["artifacts"]["latest_diff"]["available"] is True
    assert manifest["artifacts"]["latest_diff"]["identical"] is True

    latest = json.loads(files["analysis/latest_run.json"])
    assert latest["available"] is True
    assert latest["run"]["status"] == "SUCCESS"
    snapshot = json.loads(files["analysis/schema_snapshot.json"])
    assert snapshot["available"] is True

    diff = json.loads(files["diff/latest.json"])
    assert diff["available"] is True
    assert diff["identical"] is True
    assert diff["base_run_id"] != diff["target_run_id"]

    preflight = json.loads(files["validation/preflight.json"])
    assert preflight["available"] is True
    assert preflight["status"] == "READY"
    assert preflight["connection"]["current_user_exported"] is False
    assert preflight["security"]["username_exported"] is False
    assert preflight["security"]["connection_host_exported"] is False
    categories = json.loads(files["categories.json"])
    assert categories["categories"][0]["category_key"] == "U02B2B_TEST"
    assert categories["table_assignments"][0]["assignment_source"] == "MANUAL"
    assert categories["table_assignments"][0]["table_key"] == "DEMIS_OWNER.TB_PT_MST"

    report_paths = [name for name in files if name.startswith("reports/") and name.endswith(".docx")]
    assert len(report_paths) == 1
    with zipfile.ZipFile(io.BytesIO(files[report_paths[0]])) as docx:
        assert "[Content_Types].xml" in docx.namelist()
        xml = ET.fromstring(docx.read("word/document.xml"))
    text = "".join(node.text or "" for node in xml.iter()
                   if node.tag.endswith("}t"))
    assert "TB_PT_MST" in text or "PT_ID" in text


def test_fixture_credentials_not_exported(output_directory):
    for status in STATUSES:
        files = package_files(output_directory / f"final_{status}.zip")
        for path, data in files.items():
            if path.endswith(".docx"):
                # Check DOCX inner XML as well as the raw binary.
                with zipfile.ZipFile(io.BytesIO(data)) as docx:
                    nested = [docx.read(p) for p in docx.namelist() if p.endswith(".xml")]
                assert all(secret not in segment for segment in nested for secret in SENTINELS)
            assert all(secret not in data for secret in SENTINELS)


def test_tampered_persisted_zip_is_rejected(output_directory):
    files = package_files(output_directory / "final_WARNING.zip")
    original = files["categories.json"]
    files["categories.json"] = original.replace(b"U02B2B_TEST", b"U02B2B_FAKE", 1)
    assert files["categories.json"] != original
    buff = io.BytesIO()
    with zipfile.ZipFile(buff, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(PREFIX + path, content)
    with pytest.raises(CatalogPackageValidationError) as exc:
        validate_catalog_package_bytes(buff.getvalue())
    assert exc.value.code == CatalogPackageErrorCode.CHECKSUM_MISMATCH
    assert exc.value.path == "categories.json"
