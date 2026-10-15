"""U-02-C-3 synthetic backup/restore evidence seal (not a production restore API).

Checks fixed artifact names, checksums and restore summary. A passing
rehearsal NEVER confers DQA Catalog import/activation or cutover authority.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class RehearsalEvidenceError(ValueError):
    """Fail closed without leaking the underlying artifact contents."""


FILES = {
    "postgres_custom_dump": "legacy_catalog.pgcustom",
    "legacy_final_v2_zip": "legacy_final_ready.zip",
    "source_inventory": "u02c2_inventory.json",
    "restore_verification": "restore_verified.json",
}
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def _path(root: Path, filename: str) -> Path:
    target = root / filename
    if target.is_symlink() or not target.is_file():
        raise RehearsalEvidenceError("REHEARSAL_FILE_MISSING_OR_UNSAFE")
    return target


def _digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    nbytes = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            nbytes += len(chunk)
    if nbytes == 0:
        raise RehearsalEvidenceError("EMPTY_REHEARSAL_ARTIFACT")
    return nbytes, digest.hexdigest()


def _validate_report(report: dict) -> None:
    requirements = {
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
    if not isinstance(report, dict) or any(report.get(k) != v for k, v in requirements.items()):
        raise RehearsalEvidenceError("RESTORE_EVIDENCE_NOT_ACCEPTABLE")


def build_manifest(root: Path) -> dict:
    root = root.resolve(strict=True)
    report = json.loads(_path(root, "restore_verified.json").read_text("utf-8"))
    _validate_report(report)
    inventory = json.loads(_path(root, "u02c2_inventory.json").read_text("utf-8"))
    if (inventory.get("evidence_kind") != "SYNTHETIC_ISOLATED_LEGACY_PG"
            or inventory.get("cutover_allowed") is not False
            or inventory.get("table_count") != 17
            or len(inventory.get("sources", [])) != 2):
        raise RehearsalEvidenceError("SOURCE_INVENTORY_NOT_ACCEPTABLE")
    artifacts = {}
    for kind, filename in FILES.items():
        size, sha = _digest(_path(root, filename))
        artifacts[kind] = {"file": filename, "size_bytes": size, "sha256": sha}
    return {
        "schema_version": 1,
        "evidence_kind": "U02C3_SYNTHETIC_BACKUP_RESTORE",
        "artifacts": artifacts,
        "rehearsal_status": "RESTORE_REHEARSAL_ONLY",
        "source_to_dqa_mapping": "UNRESOLVED_PENDING_APPROVAL",
        "backup_restorable_in_test_db": True,
        "cutover_allowed": False,
        "rollback_authorized": False,
        "approved_by": None,
    }


def verify_manifest(root: Path, manifest: dict) -> None:
    if not isinstance(manifest, dict):
        raise RehearsalEvidenceError("MANIFEST_INVALID")
    expected = build_manifest(root)
    if manifest != expected:
        raise RehearsalEvidenceError("REHEARSAL_MANIFEST_MISMATCH")
    for item in manifest["artifacts"].values():
        if not SHA256_RE.fullmatch(item["sha256"]):
            raise RehearsalEvidenceError("ARTIFACT_SHA_INVALID")
