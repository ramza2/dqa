"""Bounded, source-scoped multi-table DOCX export from verified Snapshot metadata.

Creates one ZIP part (up to ten per-table DOCX reports), not a background job
or whole-DEMIS dump. The reports use M2-2C's already allowlisted renderer.
Never connect to Oracle, promote Catalog, or expose SQL defaults/definitions.
"""
from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZIP_STORED, ZipFile

from app.models.schema_snapshot_revision import SchemaSnapshotRevision
from app.services.schema_snapshot_erd import SnapshotErdError, build_snapshot_erd
from app.services.schema_snapshot_history import _snapshot_from_payload
from app.services.schema_snapshot_report import (
    SnapshotReportError, build_snapshot_table_docx,
)

_MAX_TABLES_PER_PART = 10
_MAX_ZIP_BYTES = 10_000_000


class SnapshotSchemaBundleError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def build_snapshot_schema_zip(
    row: SchemaSnapshotRevision, *,
    schema_name: str,
    offset: int = 0,
    limit: int = 10,
) -> tuple[bytes, int, int | None]:
    """Return ZIP, total tables in schema, and next offset (or None).

    Every table in the requested range must render completely or the entire
    response fails; there are no silent omissions or partial successes.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= _MAX_TABLES_PER_PART:
        raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_INVALID_RANGE")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_INVALID_RANGE")
    try:
        # Reuses the same immutable v1, target-identity, fingerprint, counts and
        # physical metadata consistency validation as M2-2B/M2-2C.
        build_snapshot_erd(row)
        snapshot = _snapshot_from_payload(row.snapshot_json)
    except SnapshotErdError:
        raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_UNVERIFIABLE") from None
    except (ValueError, KeyError, TypeError, AttributeError):
        raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_UNVERIFIABLE") from None

    tables = sorted(
        (t.table_name for t in snapshot.tables if t.schema_name == schema_name)
    )
    if not tables:
        raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_SCHEMA_NOT_FOUND")
    if offset >= len(tables):
        raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_RANGE_NOT_SATISFIABLE")

    selected = tables[offset:offset + limit]
    manifest = {
        "format_version": "1",
        "status": "UNAPPROVED_SNAPSHOT_METADATA_ONLY",
        "preflight_status": "NOT_VERIFIED",
        "activation_eligible": False,
        "source_name": row.source_name,
        "snapshot_revision_id": row.id,
        "schema_fingerprint": row.schema_fingerprint,
        "schema_name": schema_name,
        "offset": offset,
        "limit": limit,
        "total_tables_in_schema": len(tables),
        "exported_table_count": len(selected),
        "next_offset": offset + len(selected) if offset + len(selected) < len(tables) else None,
        "files": [],
    }
    output = BytesIO()
    try:
        # DOCX is itself a ZIP; no second compression is useful.
        with ZipFile(output, "w", compression=ZIP_STORED) as archive:
            for i, name in enumerate(selected, start=offset + 1):
                try:
                    content = build_snapshot_table_docx(
                        row, schema_name=schema_name, table_name=name,
                    )
                except SnapshotReportError as exc:
                    code = (
                        "SNAPSHOT_SCHEMA_EXPORT_TOO_LARGE"
                        if exc.code == "SNAPSHOT_REPORT_SCOPE_TOO_LARGE"
                        else "SNAPSHOT_SCHEMA_EXPORT_UNVERIFIABLE"
                    )
                    raise SnapshotSchemaBundleError(code) from None
                # Fixed numeric archive names prevent path traversal and
                # ambiguous colliding names even for unusual DB identifiers.
                path = f"tables/table-{i:06d}.docx"
                archive.writestr(path, content)
                manifest["files"].append({
                    "ordinal_in_schema": i,
                    "schema_name": schema_name,
                    "table_name": name,
                    "file": path,
                    "sha256": sha256(content).hexdigest(),
                })
                if output.tell() > _MAX_ZIP_BYTES:
                    raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_TOO_LARGE")
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
            )
            archive.writestr(
                "README.txt",
                (
                    "DQA stored Snapshot metadata only; NOT_VERIFIED; "
                    "not DBA preflight, Catalog approval or a DEMIS access grant.\n"
                    "Database comments are metadata and may require security approval "
                    "before external sharing.\n"
                    "See manifest.json for source, fingerprint, table mapping and next_offset.\n"
                ).encode("utf-8"),
            )
    except SnapshotSchemaBundleError:
        raise
    except Exception:
        raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_FAILED") from None

    content = output.getvalue()
    if len(content) > _MAX_ZIP_BYTES:
        raise SnapshotSchemaBundleError("SNAPSHOT_SCHEMA_EXPORT_TOO_LARGE")
    return content, len(tables), manifest["next_offset"]
