"""Focused tests for Catalog Package v2 validation."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.adapters.catalog.errors import CatalogPackageErrorCode, CatalogPackageValidationError
from app.adapters.catalog.limits import PACKAGE_ROOT_NAME, CatalogPackageZipLimits
from app.services.catalog_package_validation import validate_catalog_package_bytes
from tests.catalog_package_fixtures import (
    DEFAULT_FINGERPRINT,
    DEFAULT_SOURCE,
    build_core_documents,
    build_manifest,
    build_package_zip,
    sha256_hex,
    write_zip_with_infos,
)


def _validate(archive: bytes, *, limits: CatalogPackageZipLimits | None = None):
    if limits is None:
        return validate_catalog_package_bytes(archive)
    return validate_catalog_package_bytes(archive, limits=limits)


def _expect_error(archive: bytes, code: str, *, limits: CatalogPackageZipLimits | None = None):
    with pytest.raises(CatalogPackageValidationError) as exc_info:
        _validate(archive, limits=limits)
    assert exc_info.value.code == code
    return exc_info.value


def test_valid_ready_package_succeeds() -> None:
    archive = build_package_zip(package_readiness="READY")
    result = _validate(archive)
    assert result.package_format == "demis-catalog-package"
    assert result.package_version == "2.0"
    assert result.package_readiness == "READY"
    assert result.activation_eligible is True
    assert result.source.source_name == DEFAULT_SOURCE["source_name"]
    assert result.schema_fingerprint == DEFAULT_FINGERPRINT
    assert result.files_validated > 0
    assert result.archive_sha256
    assert result.manifest_sha256


def test_valid_warning_package_not_activation_eligible() -> None:
    archive = build_package_zip(package_readiness="WARNING")
    result = _validate(archive)
    assert result.package_readiness == "WARNING"
    assert result.activation_eligible is False


def test_valid_blocked_package_not_activation_eligible() -> None:
    archive = build_package_zip(package_readiness="BLOCKED")
    result = _validate(archive)
    assert result.package_readiness == "BLOCKED"
    assert result.activation_eligible is False


def test_wrong_package_format_rejected() -> None:
    archive = build_package_zip(package_format="other-format")
    _expect_error(archive, CatalogPackageErrorCode.INVALID_PACKAGE_FORMAT)


def test_unsupported_major_version_rejected() -> None:
    archive = build_package_zip(package_version="3.0")
    _expect_error(archive, CatalogPackageErrorCode.UNSUPPORTED_VERSION)


def test_minor_version_2_x_accepted() -> None:
    archive = build_package_zip(package_version="2.1")
    result = _validate(archive)
    assert result.package_version == "2.1"


def test_malformed_manifest_json_rejected() -> None:
    archive = build_package_zip(manifest_override=b"{not-json")
    _expect_error(archive, CatalogPackageErrorCode.MALFORMED_MANIFEST)


def test_missing_required_file_rejected() -> None:
    archive = build_package_zip(omit_files={"tables.json"})
    _expect_error(archive, CatalogPackageErrorCode.MISSING_REQUIRED_FILE)


def test_checksum_mismatch_rejected() -> None:
    files = build_core_documents()
    manifest = json.loads(build_manifest(files))
    for entry in manifest["files"]:
        if entry["path"] == "tables.json":
            entry["sha256"] = "0" * 64
    archive = build_package_zip(manifest_override=json.dumps(manifest).encode("utf-8"))
    _expect_error(archive, CatalogPackageErrorCode.CHECKSUM_MISMATCH)


def test_bytes_mismatch_rejected() -> None:
    files = build_core_documents()
    manifest = json.loads(build_manifest(files))
    for entry in manifest["files"]:
        if entry["path"] == "tables.json":
            entry["bytes"] = entry["bytes"] + 10
    archive = build_package_zip(manifest_override=json.dumps(manifest).encode("utf-8"))
    _expect_error(archive, CatalogPackageErrorCode.BYTES_MISMATCH)


def test_duplicate_zip_entry_rejected() -> None:
    files = build_core_documents()
    manifest = build_manifest(files)
    payload = files["tables.json"]
    entries = [
        (f"{PACKAGE_ROOT_NAME}/", b""),
        (f"{PACKAGE_ROOT_NAME}/manifest.json", manifest),
        (f"{PACKAGE_ROOT_NAME}/tables.json", payload),
        (f"{PACKAGE_ROOT_NAME}/tables.json", payload),
    ]
    # zipfile.writestr overwrites same name — use ZipFile.writestr twice via low-level.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        zf.writestr(f"{PACKAGE_ROOT_NAME}/", b"")
        zf.writestr(f"{PACKAGE_ROOT_NAME}/manifest.json", manifest)
        info1 = zipfile.ZipInfo(f"{PACKAGE_ROOT_NAME}/tables.json")
        info2 = zipfile.ZipInfo(f"{PACKAGE_ROOT_NAME}/tables.json")
        zf.writestr(info1, payload)
        zf.writestr(info2, payload)
        for path, data in files.items():
            if path == "tables.json":
                continue
            zf.writestr(f"{PACKAGE_ROOT_NAME}/{path}", data)
    archive = buffer.getvalue()
    # Confirm ZipFile exposes duplicate names.
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        assert zf.namelist().count(f"{PACKAGE_ROOT_NAME}/tables.json") == 2
    _expect_error(archive, CatalogPackageErrorCode.DUPLICATE_ENTRY)


def test_duplicate_normalized_path_rejected() -> None:
    files = build_core_documents()
    manifest = build_manifest(files)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        zf.writestr(f"{PACKAGE_ROOT_NAME}/manifest.json", manifest)
        zf.writestr(f"{PACKAGE_ROOT_NAME}/./tables.json", files["tables.json"])
        for path, data in files.items():
            if path == "tables.json":
                continue
            zf.writestr(f"{PACKAGE_ROOT_NAME}/{path}", data)
    # "./tables.json" normalizes to tables.json which also exists — if only one tables,
    # add both forms:
    archive = buffer.getvalue()
    # Rebuild explicitly with both demis_catalog_package/tables.json and
    # demis_catalog_package/./tables.json
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        zf.writestr(f"{PACKAGE_ROOT_NAME}/manifest.json", manifest)
        zf.writestr(f"{PACKAGE_ROOT_NAME}/tables.json", files["tables.json"])
        zf.writestr(f"{PACKAGE_ROOT_NAME}/./tables.json", files["tables.json"])
        for path, data in files.items():
            if path == "tables.json":
                continue
            zf.writestr(f"{PACKAGE_ROOT_NAME}/{path}", data)
    _expect_error(buffer.getvalue(), CatalogPackageErrorCode.DUPLICATE_ENTRY)


def test_parent_traversal_rejected() -> None:
    archive = build_package_zip(
        zip_entries=[
            (f"{PACKAGE_ROOT_NAME}/manifest.json", b"{}"),
            (f"{PACKAGE_ROOT_NAME}/../evil.json", b"{}"),
        ]
    )
    _expect_error(archive, CatalogPackageErrorCode.UNSAFE_PATH)


def test_absolute_path_rejected() -> None:
    archive = build_package_zip(zip_entries=[("/tmp/evil.json", b"{}")])
    _expect_error(archive, CatalogPackageErrorCode.UNSAFE_PATH)


def test_backslash_traversal_rejected() -> None:
    archive = build_package_zip(
        zip_entries=[(rf"{PACKAGE_ROOT_NAME}\..\windows\evil.json", b"{}")]
    )
    _expect_error(archive, CatalogPackageErrorCode.UNSAFE_PATH)


def test_symlink_entry_rejected() -> None:
    files = build_core_documents()
    manifest = build_manifest(files)
    infos: list[tuple[zipfile.ZipInfo, bytes]] = []
    root = zipfile.ZipInfo(f"{PACKAGE_ROOT_NAME}/")
    root.external_attr = (0o040755 << 16) | 0x10
    infos.append((root, b""))
    man = zipfile.ZipInfo(f"{PACKAGE_ROOT_NAME}/manifest.json")
    infos.append((man, manifest))
    for path, data in files.items():
        info = zipfile.ZipInfo(f"{PACKAGE_ROOT_NAME}/{path}")
        if path == "PACKAGE_README.md":
            # Unix symlink mode
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            infos.append((info, b"target"))
        else:
            infos.append((info, data))
    archive = write_zip_with_infos(infos)
    _expect_error(archive, CatalogPackageErrorCode.NON_REGULAR_ENTRY)


def test_unexpected_unmanaged_file_rejected() -> None:
    archive = build_package_zip(extra_files={"secrets/extra.json": b'{"x":1}'})
    # extra file is included in ZIP via build_package_zip but also added to
    # files before manifest — need unmanaged: present in ZIP but not manifest.
    files = build_core_documents()
    manifest = build_manifest(files)  # does not include evil.json
    entries = [(f"{PACKAGE_ROOT_NAME}/manifest.json", manifest)]
    for path, data in files.items():
        entries.append((f"{PACKAGE_ROOT_NAME}/{path}", data))
    entries.append((f"{PACKAGE_ROOT_NAME}/evil.json", b'{"nope":true}'))
    archive = build_package_zip(zip_entries=entries)
    _expect_error(archive, CatalogPackageErrorCode.UNEXPECTED_FILE)


def test_excessive_entry_count_rejected() -> None:
    limits = CatalogPackageZipLimits(max_entry_count=3)
    archive = build_package_zip()
    _expect_error(archive, CatalogPackageErrorCode.TOO_MANY_ENTRIES, limits=limits)


def test_excessive_uncompressed_or_ratio_rejected() -> None:
    limits = CatalogPackageZipLimits(
        max_uncompressed_file_bytes=50,
        max_uncompressed_total_bytes=10_000,
        max_compression_ratio=100.0,
    )
    archive = build_package_zip(
        mutate_files={"PACKAGE_README.md": b"x" * 200},
    )
    _expect_error(archive, CatalogPackageErrorCode.UNCOMPRESSED_TOO_LARGE, limits=limits)

    # Compression ratio: highly compressible payload with very low ratio limit.
    big = b"aaaa" * 5000
    files = build_core_documents()
    files["PACKAGE_README.md"] = big
    manifest = build_manifest(files)
    entries = [(f"{PACKAGE_ROOT_NAME}/manifest.json", manifest)]
    for path, data in files.items():
        entries.append((f"{PACKAGE_ROOT_NAME}/{path}", data))
    archive = build_package_zip(zip_entries=entries)
    ratio_limits = CatalogPackageZipLimits(max_compression_ratio=1.5)
    _expect_error(archive, CatalogPackageErrorCode.COMPRESSION_RATIO, limits=ratio_limits)


def test_malformed_required_json_rejected() -> None:
    archive = build_package_zip(mutate_files={"tables.json": b"{bad"})
    # Manifest bytes/sha built from mutated files inside build_package_zip — good.
    _expect_error(archive, CatalogPackageErrorCode.MALFORMED_JSON)


def test_source_identity_mismatch_rejected() -> None:
    files = build_core_documents()
    # Manifest source differs from database.json source.
    manifest = build_manifest(
        files,
        source={
            **DEFAULT_SOURCE,
            "source_name": "other_source",
        },
    )
    archive = build_package_zip(manifest_override=manifest)
    _expect_error(archive, CatalogPackageErrorCode.SOURCE_MISMATCH)


def test_schema_fingerprint_mismatch_rejected() -> None:
    files = build_core_documents(fingerprint="fp-db")
    manifest = build_manifest(files, fingerprint="fp-manifest")
    archive = build_package_zip(files=files, manifest_override=manifest)
    _expect_error(archive, CatalogPackageErrorCode.FINGERPRINT_MISMATCH)


def test_counts_mismatch_rejected() -> None:
    archive = build_package_zip(counts={"tables": 99, "columns": 1, "relations": 0, "indexes": 0, "categories": 1})
    _expect_error(archive, CatalogPackageErrorCode.COUNTS_MISMATCH)


def test_validate_api_ready_package(client: TestClient) -> None:
    archive = build_package_zip(package_readiness="READY")
    response = client.post(
        "/api/v1/catalog/packages/validate",
        files={"file": ("pkg.zip", archive, "application/zip")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["activation_eligible"] is True
    assert payload["package_readiness"] == "READY"
    assert payload["archive_sha256"] == sha256_hex(archive)


def test_validate_api_rejects_bad_format(client: TestClient) -> None:
    archive = build_package_zip(package_format="nope")
    response = client.post(
        "/api/v1/catalog/packages/validate",
        files={"file": ("pkg.zip", archive, "application/zip")},
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == CatalogPackageErrorCode.INVALID_PACKAGE_FORMAT
    assert "password" not in detail["message"].lower()
