"""Offline SchemaSnapshot -> Catalog Package v2 WARNING candidate.

No Oracle connection, credentials, persistence, REST endpoint, or activation.
A candidate is never eligible for activation without separate DB preflight and
reviewed READY transition. This builder cannot issue READY packages.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from app.adapters.catalog.limits import PACKAGE_FORMAT, PACKAGE_ROOT_NAME
from app.adapters.schema_inspector.base import SchemaSnapshot
from app.services.catalog_package_validation import validate_catalog_package_bytes

_SOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_VERSION = "2.0"
_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sort_and_dump(items: list[Any], *, key) -> list[dict[str, Any]]:
    return [asdict(x) for x in sorted(items, key=key)]


def _physical_payload(snapshot: SchemaSnapshot) -> dict[str, Any]:
    """Normalized, sorted physical metadata; never contains user/host/password."""
    return {
        "snapshot_version": 1,
        "db_type": snapshot.db_type,
        "database_name": snapshot.database_name,
        "schema_name": snapshot.schema_name,
        "tables": _sort_and_dump(
            snapshot.tables, key=lambda x: (x.schema_name, x.table_name)
        ),
        "columns": [
            {**row, "default_value": None}
            for row in _sort_and_dump(
                snapshot.columns,
                key=lambda x: (x.schema_name, x.table_name, x.ordinal_position, x.column_name),
            )
        ],
        "primary_keys": _sort_and_dump(
            snapshot.primary_keys,
            key=lambda x: (x.schema_name, x.table_name, x.constraint_name, x.ordinal_position),
        ),
        "unique_constraints": _sort_and_dump(
            snapshot.unique_constraints,
            key=lambda x: (x.schema_name, x.table_name, x.constraint_name, x.ordinal_position),
        ),
        "foreign_keys": _sort_and_dump(
            snapshot.foreign_keys,
            key=lambda x: (x.schema_name, x.source_table, x.constraint_name),
        ),
        "indexes": [
            {**row, "index_definition": None}
            for row in _sort_and_dump(
                snapshot.indexes,
                key=lambda x: (x.schema_name, x.table_name, x.index_name),
            )
        ],
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_bytes(payload)).hexdigest()


def _single_column_unique_keys(snapshot: SchemaSnapshot) -> set[tuple[str, str, str]]:
    """Match the legacy Analyzer: column-level unique means unique *alone*.

    Include single-column UNIQUE constraints, PRIMARY KEYs and unique indexes.
    Composite members are not individually unique merely by participation.
    """
    result: set[tuple[str, str, str]] = set()
    for rows in (snapshot.unique_constraints, snapshot.primary_keys):
        grouped: dict[tuple[str, str, str], list[str]] = {}
        for item in rows:
            key = (item.schema_name, item.table_name, item.constraint_name)
            grouped.setdefault(key, []).append(item.column_name)
        for (schema, table, _constraint), cols in grouped.items():
            if len(cols) == 1:
                result.add((schema, table, cols[0]))

    for idx in snapshot.indexes:
        if idx.is_unique and len(idx.columns) == 1:
            result.add((idx.schema_name, idx.table_name, idx.columns[0].column_name))
    return result


def _catalog_documents(
    snapshot: SchemaSnapshot, source_name: str, generated_at: datetime
) -> tuple[dict[str, Any], dict[str, bytes]]:
    physical = _physical_payload(snapshot)
    fp = _fingerprint(physical)
    identity = {
        "source_name": source_name,
        "db_type": snapshot.db_type,
        "database_name": snapshot.database_name,
        "default_schema": snapshot.schema_name,
    }
    pk_cols = {(p.schema_name, p.table_name, p.column_name) for p in snapshot.primary_keys}
    unique_single = _single_column_unique_keys(snapshot)

    tables = [
        {
            "schema_name": t.schema_name,
            "table_name": t.table_name,
            "table_type": t.table_type,
            "table_comment": t.table_comment,
        }
        for t in sorted(snapshot.tables, key=lambda t: (t.schema_name, t.table_name))
    ]
    columns = [
        {
            "schema_name": c.schema_name,
            "table_name": c.table_name,
            "column_name": c.column_name,
            "ordinal_position": c.ordinal_position,
            "data_type": c.data_type,
            "character_maximum_length": c.character_maximum_length,
            "numeric_precision": c.numeric_precision,
            "numeric_scale": c.numeric_scale,
            "nullable": c.is_nullable,
            "column_comment": c.column_comment,
            "primary_key": (c.schema_name, c.table_name, c.column_name) in pk_cols,
            "unique": (c.schema_name, c.table_name, c.column_name) in unique_single,
            # Never export potentially sensitive SQL default expressions.
            "default_value": None,
        }
        for c in sorted(
            snapshot.columns,
            key=lambda c: (c.schema_name, c.table_name, c.ordinal_position, c.column_name),
        )
    ]
    relations = [
        {
            "constraint_name": fk.constraint_name,
            "schema_name": fk.schema_name,
            "table_name": fk.source_table,
            "referenced_schema": fk.target_schema,
            "referenced_table": fk.target_table,
            "column_mapping": [
                {
                    "ordinal_position": item.ordinal_position,
                    "source_column": item.source_column,
                    "target_column": item.target_column,
                }
                for item in sorted(fk.columns, key=lambda x: x.ordinal_position)
            ],
        }
        for fk in sorted(
            snapshot.foreign_keys,
            key=lambda fk: (fk.schema_name, fk.source_table, fk.constraint_name),
        )
    ]
    indexes = [
        {
            "schema_name": ix.schema_name,
            "table_name": ix.table_name,
            "index_name": ix.index_name,
            "unique": ix.is_unique,
            "index_method": ix.index_method,
            "columns": [
                c.column_name for c in sorted(ix.columns, key=lambda c: c.ordinal_position)
            ],
        }
        for ix in sorted(
            snapshot.indexes, key=lambda ix: (ix.schema_name, ix.table_name, ix.index_name)
        )
    ]
    counts = {
        "tables": len(tables), "columns": len(columns),
        "relations": len(relations), "indexes": len(indexes),
        "categories": 0, "category_assignments": 0,
    }
    documents = {
        "database.json": {
            "source": identity,
            "latest_analysis": {
                "schema_fingerprint": fp,
                "status": "SUCCESS",
                "generated_at": generated_at.isoformat(),
                "metadata_only": True,
            },
        },
        "tables.json": {"tables": tables},
        "columns.json": {"columns": columns},
        "relations.json": {"relations": relations},
        "indexes.json": {"indexes": indexes},
        "categories.json": {
            "categories": [],
            "table_assignments": [],
        },
        "erd.json": {
            "nodes": [
                {"schema_name": t["schema_name"], "table_name": t["table_name"]}
                for t in tables
            ],
            "edges": [
                {
                    "constraint_name": fk["constraint_name"],
                    "source_table": fk["table_name"],
                    "target_schema": fk["referenced_schema"],
                    "target_table": fk["referenced_table"],
                }
                for fk in relations
            ],
        },
        "analysis/latest_run.json": {
            "available": True,
            "run": {
                "status": "SUCCESS",
                "target_schema": snapshot.schema_name,
                "schema_fingerprint": fp,
                "generated_at": generated_at.isoformat(),
                "counts": counts,
                "origin": "dqa-schema-inspector",
            },
        },
        "analysis/schema_snapshot.json": {
            "available": True,
            "snapshot_version": 1,
            "payload": {
                "schema_fingerprint": fp,
                **physical,
            },
        },
        "validation/preflight.json": {
            "available": False,
            "status": "NOT_AVAILABLE",
            "reason": "No independent DBA-approved metadata preflight was performed.",
        },
        "diff/latest.json": {
            "available": False,
            "reason": "No verified previous Snapshot for comparison.",
            "identical": None,
            "changes": [],
        },
    }
    return {"source": identity, "fingerprint": fp, "counts": counts}, {
        path: _json_bytes(body) for path, body in documents.items()
    }


def build_catalog_v2_candidate(
    snapshot: SchemaSnapshot,
    *,
    source_name: str,
    generated_at: datetime | None = None,
) -> bytes:
    """Build + self-validate an importable, non-activatable Catalog v2 ZIP.

    Consumers must not treat the validated candidate as a READY package.
    API/persistence/activation are deliberately outside this pure builder.
    """
    if not _SOURCE_NAME.fullmatch(source_name):
        raise ValueError("invalid source_name")
    if (
        snapshot.db_type.casefold() != "oracle"
        or not snapshot.database_name
        or not snapshot.schema_name
        or not snapshot.tables
    ):
        raise ValueError("Oracle SchemaSnapshot must be complete and non-empty")
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)
    if generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")
    generated_at = generated_at.astimezone(timezone.utc)

    metadata, files = _catalog_documents(snapshot, source_name, generated_at)
    manifest = {
        "package_format": PACKAGE_FORMAT,
        "package_version": _VERSION,
        "package_readiness": "WARNING",
        "readiness_issues": ["Independent metadata preflight and change review not yet verified."],
        "source": metadata["source"],
        "schema_fingerprint": metadata["fingerprint"],
        "generated_at": generated_at.isoformat(),
        "counts": metadata["counts"],
        "security": {
            "metadata_select_only": True,
            "business_data_selected": False,
            "credentials_exported": False,
            "connection_host_exported": False,
        },
        "files": [
            {"path": path, "bytes": len(data),
             "sha256": hashlib.sha256(data).hexdigest()}
            for path, data in sorted(files.items())
        ],
    }
    content = {"manifest.json": _json_bytes(manifest), **files}

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path, data in sorted(content.items()):
            info = zipfile.ZipInfo(
                filename=f"{PACKAGE_ROOT_NAME}/{relative_path}",
                date_time=_ZIP_TIME,
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    result = buffer.getvalue()
    validated = validate_catalog_package_bytes(result)
    if validated.package_readiness != "WARNING" or validated.activation_eligible:
        raise ValueError("candidate must not be activation eligible")
    return result
