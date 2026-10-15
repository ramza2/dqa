"""U-02-C-3: native disposable PG dump→restore evidence + fail-closed gate.

The fixture is entirely synthetic. Neither DQA import nor activation occurs.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.services.catalog_package_validation import validate_catalog_package_bytes
from tests.u02c3_backup_gate import (
    FILES,
    RehearsalEvidenceError,
    build_manifest,
    verify_manifest,
)


def _report():
    return {
        "evidence_kind": "U02C3_SYNTHETIC_PG_RESTORE_ONLY",
        "original_inventory_equal": True,
        "restored_inventory_equal": True,
        "row_digest_equal": True,
        "checked_tables": 17,
        "checked_extra_tables": 1,
        "source_count": 2,
        "reader_role": "SELECT_ONLY",
        "transaction": "REPEATABLE_READ_READ_ONLY",
        "dqa_catalog_modified": False,
        "dqa_import_revision_id": None,
        "dqa_active_catalog_modified": False,
        "cutover_allowed": False,
        "rollback_authorized": False,
    }


def _synthetic_files(directory: Path):
    (directory / FILES["postgres_custom_dump"]).write_bytes(b"PGDMP-synthetic")
    (directory / FILES["legacy_final_v2_zip"]).write_bytes(b"PK-synthetic")
    (directory / FILES["source_inventory"]).write_text(json.dumps({
        "evidence_kind": "SYNTHETIC_ISOLATED_LEGACY_PG",
        "table_count": 17, "cutover_allowed": False,
        "sources": [{"source_alias": "SRC_001"}, {"source_alias": "SRC_002"}],
    }))
    (directory / FILES["restore_verification"]).write_text(json.dumps(_report()))


def test_manifest_checksums_and_explicit_no_cutover(tmp_path):
    _synthetic_files(tmp_path)
    manifest = build_manifest(tmp_path)
    verify_manifest(tmp_path, manifest)
    assert manifest["schema_version"] == 1
    assert manifest["rehearsal_status"] == "RESTORE_REHEARSAL_ONLY"
    assert manifest["source_to_dqa_mapping"] == "UNRESOLVED_PENDING_APPROVAL"
    assert manifest["cutover_allowed"] is False
    assert manifest["rollback_authorized"] is False
    assert manifest["approved_by"] is None
    assert set(manifest["artifacts"]) == set(FILES)


def test_tampered_pg_dump_digest_rejected(tmp_path):
    _synthetic_files(tmp_path)
    manifest = build_manifest(tmp_path)
    with (tmp_path / FILES["postgres_custom_dump"]).open("ab") as stream:
        stream.write(b"unauthorized-change")
    with pytest.raises(RehearsalEvidenceError, match="MANIFEST_MISMATCH"):
        verify_manifest(tmp_path, manifest)


@pytest.mark.parametrize("key,value", [
    ("cutover_allowed", True),
    ("rollback_authorized", True),
    ("approved_by", "implicit"),
    ("source_to_dqa_mapping", "RESOLVED"),
    ("rehearsal_status", "READY"),
])
def test_no_authority_can_be_injected_in_manifest(tmp_path, key, value):
    _synthetic_files(tmp_path)
    manifest = build_manifest(tmp_path)
    manifest[key] = value
    with pytest.raises(RehearsalEvidenceError, match="MANIFEST_MISMATCH"):
        verify_manifest(tmp_path, manifest)


@pytest.mark.parametrize("field,value", [
    ("cutover_allowed", True),
    ("rollback_authorized", True),
    ("reader_role", "ADMIN"),
    ("restored_inventory_equal", False),
    ("row_digest_equal", False),
    ("dqa_active_catalog_modified", True),
    ("dqa_import_revision_id", 1),
])
def test_invalid_restore_proof_rejected(tmp_path, field, value):
    _synthetic_files(tmp_path)
    report_path = tmp_path / FILES["restore_verification"]
    result = json.loads(report_path.read_text("utf-8"))
    result[field] = value
    report_path.write_text(json.dumps(result))
    with pytest.raises(RehearsalEvidenceError, match="RESTORE_EVIDENCE_NOT_ACCEPTABLE"):
        build_manifest(tmp_path)


def test_symlink_or_missing_artifact_rejected(tmp_path):
    _synthetic_files(tmp_path)
    dump = tmp_path / FILES["postgres_custom_dump"]
    dump.unlink()
    with pytest.raises(RehearsalEvidenceError, match="REHEARSAL_FILE_MISSING_OR_UNSAFE"):
        build_manifest(tmp_path)


@pytest.fixture(scope="module")
def sealed_rehearsal():
    value = os.environ.get("DQA_U02C3_ARTIFACT_DIR")
    if not value:
        pytest.skip("set DQA_U02C3_ARTIFACT_DIR for native PG restore integration")
    root = Path(value).resolve(strict=True)
    manifest = json.loads((root / "rehearsal_manifest.json").read_text("utf-8"))
    verify_manifest(root, manifest)
    return root, manifest


def test_real_restore_evidence_is_verified_but_not_authority(sealed_rehearsal):
    root, manifest = sealed_rehearsal
    assert manifest["evidence_kind"] == "U02C3_SYNTHETIC_BACKUP_RESTORE"
    assert manifest["backup_restorable_in_test_db"] is True
    assert manifest["cutover_allowed"] is False
    assert manifest["rollback_authorized"] is False
    assert manifest["approved_by"] is None
    backup = root / FILES["postgres_custom_dump"]
    assert backup.read_bytes()[:5] == b"PGDMP"
    report = json.loads((root / FILES["restore_verification"]).read_text("utf-8"))
    assert report["row_digest_equal"] is True
    assert report["dqa_import_revision_id"] is None


def test_genuine_legacy_v2_zip_validates_without_import_or_activation(sealed_rehearsal):
    root, manifest = sealed_rehearsal
    content = (root / FILES["legacy_final_v2_zip"]).read_bytes()
    validated = validate_catalog_package_bytes(content)
    assert validated.package_format == "demis-catalog-package"
    assert validated.package_version == "2.0"
    assert validated.package_readiness == "READY"
    # DQA structural validator eligibility is NOT independent authority.
    assert validated.activation_eligible is True
    assert manifest["cutover_allowed"] is False
    assert manifest["source_to_dqa_mapping"] == "UNRESOLVED_PENDING_APPROVAL"
