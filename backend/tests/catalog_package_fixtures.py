"""In-memory Catalog Package v2 ZIP builders for tests (no large binary fixtures)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from typing import Any

from app.adapters.catalog.limits import PACKAGE_ROOT_NAME

DEFAULT_SOURCE = {
    "source_name": "oracle_demis_mock",
    "db_type": "oracle",
    "database_name": "FREEPDB1",
    "default_schema": "DEMIS_OWNER",
}
DEFAULT_FINGERPRINT = "fp-test-001"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def build_core_documents(
    *,
    source: dict[str, Any] | None = None,
    fingerprint: str = DEFAULT_FINGERPRINT,
    tables: list[Any] | None = None,
    columns: list[Any] | None = None,
    relations: list[Any] | None = None,
    indexes: list[Any] | None = None,
    categories: list[Any] | None = None,
) -> dict[str, bytes]:
    """Build producer-compatible Catalog Package v2 core files."""
    source = source or dict(DEFAULT_SOURCE)
    tables = tables if tables is not None else [{"schema": "DEMIS_OWNER", "name": "T1"}]
    columns = columns if columns is not None else [{"table": "T1", "name": "ID"}]
    relations = relations if relations is not None else []
    indexes = indexes if indexes is not None else []
    categories = categories if categories is not None else [{"id": "cat1"}]

    return {
        "database.json": _json_bytes(
            {
                "source": source,
                "latest_analysis": {"schema_fingerprint": fingerprint},
            }
        ),
        "tables.json": _json_bytes({"tables": tables}),
        "columns.json": _json_bytes({"columns": columns}),
        "relations.json": _json_bytes({"relations": relations}),
        "indexes.json": _json_bytes({"indexes": indexes}),
        "categories.json": _json_bytes(
            {
                "categories": categories,
                "table_assignments": [],
            }
        ),
        "erd.json": _json_bytes({"nodes": [], "edges": []}),
        # Schema Analyzer producer v2 shape (nested run).
        "analysis/latest_run.json": _json_bytes(
            {
                "available": True,
                "run": {
                    "run_id": 3,
                    "status": "SUCCESS",
                    "target_schema": source.get("default_schema"),
                    "schema_fingerprint": fingerprint,
                    "counts": {
                        "tables": len(tables),
                        "columns": len(columns),
                        "relations": len(relations),
                        "indexes": len(indexes),
                    },
                },
            }
        ),
        "analysis/schema_snapshot.json": _json_bytes(
            {
                "available": True,
                "run_id": 3,
                "payload": {
                    "schema_fingerprint": fingerprint,
                    "objects": [],
                },
            }
        ),
        "validation/preflight.json": _json_bytes(
            {
                "available": True,
                "status": "READY",
                "checks": [],
            }
        ),
        "diff/latest.json": _json_bytes(
            {
                "available": True,
                "changed": False,
                "entries": [],
            }
        ),
        "PACKAGE_README.md": b"# Catalog Package\n",
        "diff/latest_summary.md": b"No changes\n",
        "reports/sample.docx": b"PK\x03\x04fake-docx-bytes",
    }


def build_manifest(
    files: dict[str, bytes],
    *,
    package_format: str = "demis-catalog-package",
    package_version: str = "2.0",
    package_readiness: str = "READY",
    source: dict[str, Any] | None = None,
    fingerprint: str = DEFAULT_FINGERPRINT,
    counts: dict[str, Any] | None = None,
    include_paths: list[str] | None = None,
) -> bytes:
    source = source or dict(DEFAULT_SOURCE)
    paths = include_paths if include_paths is not None else sorted(files.keys())
    managed = []
    for path in paths:
        data = files[path]
        managed.append(
            {
                "path": path,
                "sha256": sha256_hex(data),
                "bytes": len(data),
            }
        )
    if counts is None:
        counts = {}
        for key, filename, list_key in (
            ("tables", "tables.json", "tables"),
            ("columns", "columns.json", "columns"),
            ("relations", "relations.json", "relations"),
            ("indexes", "indexes.json", "indexes"),
            ("categories", "categories.json", "categories"),
        ):
            raw = files.get(filename)
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and isinstance(payload.get(list_key), list):
                counts[key] = len(payload[list_key])

    manifest = {
        "package_format": package_format,
        "package_version": package_version,
        "package_readiness": package_readiness,
        "source": source,
        "schema_fingerprint": fingerprint,
        "generated_at": "2026-09-21T08:15:30+00:00",
        "counts": counts,
        "files": managed,
    }
    return _json_bytes(manifest)


def build_package_zip(
    *,
    package_readiness: str = "READY",
    package_format: str = "demis-catalog-package",
    package_version: str = "2.0",
    source: dict[str, Any] | None = None,
    fingerprint: str = DEFAULT_FINGERPRINT,
    files: dict[str, bytes] | None = None,
    mutate_files: dict[str, bytes] | None = None,
    omit_files: set[str] | None = None,
    extra_files: dict[str, bytes] | None = None,
    manifest_override: bytes | None = None,
    counts: dict[str, Any] | None = None,
    include_root_dir: bool = True,
    zip_entries: list[tuple[str, bytes]] | None = None,
) -> bytes:
    """Build a Catalog Package ZIP.

    If zip_entries is provided, write those raw entries instead of the standard layout
    (used for path-traversal / duplicate / symlink adversarial cases).
    """
    if zip_entries is not None:
        return _write_entries(zip_entries)

    package_files = dict(files) if files is not None else build_core_documents(
        source=source, fingerprint=fingerprint
    )
    if mutate_files:
        package_files.update(mutate_files)
    if omit_files:
        for path in omit_files:
            package_files.pop(path, None)
    if extra_files:
        package_files.update(extra_files)

    manifest = manifest_override or build_manifest(
        package_files,
        package_format=package_format,
        package_version=package_version,
        package_readiness=package_readiness,
        source=source,
        fingerprint=fingerprint,
        counts=counts,
    )

    entries: list[tuple[str, bytes]] = []
    if include_root_dir:
        entries.append((f"{PACKAGE_ROOT_NAME}/", b""))
    entries.append((f"{PACKAGE_ROOT_NAME}/manifest.json", manifest))
    for path, data in sorted(package_files.items()):
        entries.append((f"{PACKAGE_ROOT_NAME}/{path}", data))
    return _write_entries(entries)


def package_with_manifest_path_override(bad_path: str) -> bytes:
    """Valid package bytes whose manifest.files lists an unsafe path (for reject tests)."""
    files = build_core_documents()
    manifest = json.loads(build_manifest(files))
    # Point the first managed entry at an unsafe path while keeping digest metadata.
    manifest["files"][0]["path"] = bad_path
    return build_package_zip(files=files, manifest_override=_json_bytes(manifest))


def _write_entries(entries: list[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            if name.endswith("/") and not data:
                zf.writestr(name, b"")
            else:
                zf.writestr(name, data)
    return buffer.getvalue()


def write_zip_with_infos(infos_and_data: list[tuple[zipfile.ZipInfo, bytes]]) -> bytes:
    """Low-level ZIP writer for adversarial ZipInfo attributes (symlink, etc.)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as zf:
        for info, data in infos_and_data:
            zf.writestr(info, data)
    return buffer.getvalue()
