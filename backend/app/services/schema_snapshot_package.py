"""Pure SchemaSnapshot -> Catalog Package v2 candidate builder.

No Oracle connection, credentials, Catalog writes, activation, preflight or
implicit READY claim. Mirrors the legacy producer's canonical physical
fingerprint and normalized document field names for DQA consumers.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.adapters.catalog.limits import PACKAGE_FORMAT, PACKAGE_ROOT_NAME
from app.adapters.schema_inspector.base import SchemaSnapshot
from app.services.catalog_package_validation import validate_catalog_package_bytes


@dataclass(frozen=True)
class CandidateCatalogPackage:
    content: bytes
    schema_fingerprint: str
    package_readiness: str = "WARNING"


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _fingerprint(payload: dict[str, Any]) -> str:
    """Match PoC fingerprint(): sorted-key compact UTF-8 SHA-256."""
    return hashlib.sha256(_json_bytes(payload)).hexdigest()


def _table_key(schema: str, table: str) -> str:
    return f"{schema}.{table}"


def schema_snapshot_fingerprint(snapshot: SchemaSnapshot) -> str:
    """Match legacy Schema Analyzer physical fingerprint, without runtime data."""
    return _fingerprint({
        "db_type": snapshot.db_type,
        "database_name": snapshot.database_name,
        "schema_name": snapshot.schema_name,
        "tables": sorted(
            [{"schema": t.schema_name, "name": t.table_name, "type": t.table_type,
              "comment": t.table_comment or ""} for t in snapshot.tables],
            key=lambda x: (x["schema"], x["name"]),
        ),
        "columns": sorted(
            [{"schema": c.schema_name, "table": c.table_name,
              "ordinal": c.ordinal_position, "name": c.column_name,
              "type": c.data_type, "nullable": c.is_nullable,
              "default": c.default_value or "", "comment": c.column_comment or ""}
             for c in snapshot.columns],
            key=lambda x: (x["schema"], x["table"], x["ordinal"]),
        ),
        "pks": sorted(
            [{"schema": k.schema_name, "table": k.table_name,
              "name": k.constraint_name, "ordinal": k.ordinal_position,
              "column": k.column_name} for k in snapshot.primary_keys],
            key=lambda x: (x["schema"], x["table"], x["name"], x["ordinal"]),
        ),
        "uniques": sorted(
            [{"schema": k.schema_name, "table": k.table_name,
              "name": k.constraint_name, "ordinal": k.ordinal_position,
              "column": k.column_name} for k in snapshot.unique_constraints],
            key=lambda x: (x["schema"], x["table"], x["name"], x["ordinal"]),
        ),
        "fks": sorted(
            [{"source_schema": fk.schema_name, "source": fk.source_table,
              "name": fk.constraint_name, "target_schema": fk.target_schema,
              "target": fk.target_table,
              "cols": [(c.source_column, c.target_column) for c in
                       sorted(fk.columns, key=lambda c: c.ordinal_position)]}
             for fk in snapshot.foreign_keys],
            key=lambda x: (x["source_schema"], x["source"], x["name"]),
        ),
        "indexes": sorted(
            [{"schema": ix.schema_name, "table": ix.table_name,
              "name": ix.index_name, "unique": ix.is_unique,
              "method": ix.index_method or "",
              "cols": [c.column_name for c in
                       sorted(ix.columns, key=lambda c: c.ordinal_position)]}
             for ix in snapshot.indexes],
            key=lambda x: (x["schema"], x["table"], x["name"]),
        ),
    })


def _normalized_documents(snapshot: SchemaSnapshot, source_name: str, fp: str) -> dict[str, Any]:
    """Produce normalized PoC-compatible v2 documents with no guessed semantics."""
    table_keys = {(t.schema_name, t.table_name) for t in snapshot.tables}
    column_keys = {(c.schema_name, c.table_name, c.column_name) for c in snapshot.columns}
    if not table_keys or len(table_keys) != len(snapshot.tables):
        raise ValueError("schema snapshot must contain unique tables")
    if len(column_keys) != len(snapshot.columns):
        raise ValueError("schema snapshot has duplicate column identifiers")
    if snapshot.db_type != "oracle" or not snapshot.schema_name or not source_name:
        raise ValueError("schema snapshot source identity is invalid")
    if any(t.schema_name != snapshot.schema_name for t in snapshot.tables):
        raise ValueError("snapshot contains tables outside its declared schema")
    if any((c.schema_name, c.table_name) not in table_keys for c in snapshot.columns):
        raise ValueError("snapshot contains orphan columns")

    grouped_keys: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    pk_keys: set[tuple[str, str, str]] = set()
    individually_unique: set[tuple[str, str, str]] = set()

    for kind, entries in (("PRIMARY_KEY", snapshot.primary_keys),
                          ("UNIQUE", snapshot.unique_constraints)):
        grouped: dict[tuple[str, str, str], list[Any]] = defaultdict(list)
        for k in entries:
            if (k.schema_name, k.table_name, k.column_name) not in column_keys:
                raise ValueError("snapshot contains unresolved key constraint columns")
            grouped[(k.schema_name, k.table_name, k.constraint_name)].append(k)
            if kind == "PRIMARY_KEY":
                pk_keys.add((k.schema_name, k.table_name, k.column_name))
        for (schema, table, name), cols in sorted(grouped.items()):
            ordered = sorted(cols, key=lambda c: c.ordinal_position)
            if len({c.ordinal_position for c in ordered}) != len(ordered):
                raise ValueError("snapshot contains duplicate constraint ordinals")
            names = [c.column_name for c in ordered]
            if len(ordered) == 1:
                individually_unique.add((schema, table, names[0]))
            grouped_keys[(schema, table)].append({
                "constraint_name": name, "constraint_type": kind, "columns": names,
            })

    for ix in snapshot.indexes:
        if (ix.schema_name, ix.table_name) not in table_keys:
            raise ValueError("snapshot contains orphan indexes")
        if ix.is_unique and len(ix.columns) == 1:
            individually_unique.add((ix.schema_name, ix.table_name, ix.columns[0].column_name))

    relations: list[dict[str, Any]] = []
    for fk in sorted(snapshot.foreign_keys,
                     key=lambda x: (x.schema_name, x.source_table, x.constraint_name)):
        src = (fk.schema_name, fk.source_table)
        target = (fk.target_schema, fk.target_table)
        # Do not silently truncate relationships to outside the inspected scope.
        if src not in table_keys or target not in table_keys:
            raise ValueError("schema snapshot contains out-of-scope FK; inspect all schemas before packaging")
        mappings = []
        for m in sorted(fk.columns, key=lambda c: c.ordinal_position):
            if (*src, m.source_column) not in column_keys or (*target, m.target_column) not in column_keys:
                raise ValueError("snapshot contains unresolved FK column mapping")
            mappings.append({"ordinal_position": m.ordinal_position,
                             "source_column": m.source_column,
                             "target_column": m.target_column})
        if not mappings:
            raise ValueError("snapshot contains empty FK mapping")
        relation_key = f"{_table_key(*src)}::{fk.constraint_name}"
        relations.append({
            "relation_key": relation_key, "constraint_name": fk.constraint_name,
            "relation_type": "FOREIGN_KEY",
            "source_table_key": _table_key(*src),
            "target_table_key": _table_key(*target),
            "column_mapping": mappings,
            "object_fingerprint": _fingerprint({
                "source_schema": fk.schema_name, "source_table": fk.source_table,
                "constraint_name": fk.constraint_name, "target_schema": fk.target_schema,
                "target_table": fk.target_table,
                "columns": [{"source": m["source_column"], "target": m["target_column"]}
                            for m in mappings],
            }),
        })

    tables = []
    for t in sorted(snapshot.tables, key=lambda x: (x.schema_name, x.table_name)):
        tables.append({
            "table_key": _table_key(t.schema_name, t.table_name),
            "schema_name": t.schema_name, "table_name": t.table_name,
            "table_type": t.table_type, "table_comment": t.table_comment,
            "comment_provenance": "DB_COMMENT" if t.table_comment else None,
            "object_fingerprint": _fingerprint({
                "schema_name": t.schema_name, "table_name": t.table_name,
                "table_type": t.table_type, "table_comment": t.table_comment or "",
            }),
            "key_constraints": grouped_keys.get((t.schema_name, t.table_name), []),
            "categories": [],
        })
    columns = []
    for c in sorted(snapshot.columns, key=lambda x: (
        x.schema_name, x.table_name, x.ordinal_position, x.column_name
    )):
        columns.append({
            "column_key": f"{_table_key(c.schema_name, c.table_name)}.{c.column_name}",
            "table_key": _table_key(c.schema_name, c.table_name),
            "ordinal_position": c.ordinal_position, "column_name": c.column_name,
            "data_type": c.data_type,
            "character_maximum_length": c.character_maximum_length,
            "numeric_precision": c.numeric_precision, "numeric_scale": c.numeric_scale,
            "nullable": c.is_nullable, "default_value": c.default_value,
            "column_comment": c.column_comment,
            "comment_provenance": "DB_COMMENT" if c.column_comment else None,
            "primary_key": (c.schema_name, c.table_name, c.column_name) in pk_keys,
            "unique": (c.schema_name, c.table_name, c.column_name) in individually_unique,
            "object_fingerprint": _fingerprint({
                "schema_name": c.schema_name, "table_name": c.table_name,
                "ordinal_position": c.ordinal_position, "column_name": c.column_name,
                "data_type": c.data_type, "is_nullable": c.is_nullable,
                "default_value": c.default_value or "",
                "column_comment": c.column_comment or "",
            }),
        })
    indexes = []
    for ix in sorted(snapshot.indexes, key=lambda x: (x.schema_name, x.table_name, x.index_name)):
        ordered = sorted(ix.columns, key=lambda c: c.ordinal_position)
        indexes.append({
            "index_key": f"{_table_key(ix.schema_name, ix.table_name)}::{ix.index_name}",
            "table_key": _table_key(ix.schema_name, ix.table_name),
            "index_name": ix.index_name, "unique": ix.is_unique,
            "index_method": ix.index_method, "index_definition": ix.index_definition,
            "columns": [c.column_name for c in ordered],
            "object_fingerprint": _fingerprint({
                "schema_name": ix.schema_name, "table_name": ix.table_name,
                "index_name": ix.index_name, "is_unique": ix.is_unique,
                "index_method": ix.index_method or "",
                "columns": [c.column_name for c in ordered],
            }),
        })
    source = {
        "source_name": source_name, "db_type": snapshot.db_type,
        "database_name": snapshot.database_name, "default_schema": snapshot.schema_name,
    }
    counts = {
        "tables": len(tables), "columns": len(columns), "relations": len(relations),
        "indexes": len(indexes), "categories": 0, "category_assignments": 0,
    }
    run = {
        "status": "SUCCESS", "target_schema": snapshot.schema_name,
        "schema_fingerprint": fp,
        "counts": {k: counts[k] for k in ("tables", "columns", "relations", "indexes")},
        "capture_mode": "METADATA_ONLY",
    }
    return {
        "database.json": {
            "source": source, "latest_analysis": run,
            "security": {
                "connection_host_exported": False, "username_exported": False,
                "credentials_exported": False, "connection_options_exported": False,
            },
        },
        "tables.json": {"tables": tables},
        "columns.json": {"columns": columns},
        "relations.json": {"relations": relations},
        "indexes.json": {"indexes": indexes},
        "categories.json": {"categories": [], "table_assignments": []},
        "erd.json": {
            "nodes": [{
                "id": t["table_key"], "schema_name": t["schema_name"],
                "table_name": t["table_name"],
                "label": t["table_comment"] or t["table_name"], "categories": [],
            } for t in tables],
            "edges": [{
                "id": r["relation_key"], "source": r["source_table_key"],
                "target": r["target_table_key"],
                "constraint_name": r["constraint_name"],
                "relation_type": r["relation_type"],
            } for r in relations],
        },
        "analysis/latest_run.json": {"available": True, "run": run},
        "analysis/schema_snapshot.json": {
            "available": True, "run_id": None, "snapshot_version": "1",
            "capture_mode": "METADATA_ONLY",
            "payload": {
                "schema_fingerprint": fp,
                "db_type": snapshot.db_type,
                "database_name": snapshot.database_name,
                "schema_name": snapshot.schema_name,
                "tables": [asdict(t) for t in snapshot.tables],
                "columns": [asdict(c) for c in snapshot.columns],
                "primary_keys": [asdict(k) for k in snapshot.primary_keys],
                "unique_constraints": [asdict(k) for k in snapshot.unique_constraints],
                "foreign_keys": [asdict(fk) for fk in snapshot.foreign_keys],
                "indexes": [asdict(ix) for ix in snapshot.indexes],
            },
        },
        # No fabricated preflight or diff evidence: remain WARNING until checked.
        "validation/preflight.json": {
            "available": False, "status": "NOT_AVAILABLE",
            "reason": "Metadata-only candidate: no persisted analysis preflight",
        },
        "diff/latest.json": {
            "available": False,
            "reason": "No comparison to persisted prior snapshot",
        },
    }


def build_snapshot_catalog_package(
    snapshot: SchemaSnapshot,
    *,
    source_name: str,
    generated_at: datetime | None = None,
) -> CandidateCatalogPackage:
    """Build and independently validate a WARNING Catalog Package v2 ZIP.

    Deliberately does not import, write, activate, or claim READY.
    """
    now = generated_at or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("generated_at must be timezone aware")
    fp = schema_snapshot_fingerprint(snapshot)
    documents = _normalized_documents(snapshot, source_name, fp)
    files = {name: _json_bytes(doc) for name, doc in documents.items()}
    counts = {key: len(documents[file][section]) for key, file, section in (
        ("tables", "tables.json", "tables"),
        ("columns", "columns.json", "columns"),
        ("relations", "relations.json", "relations"),
        ("indexes", "indexes.json", "indexes"),
        ("categories", "categories.json", "categories"),
        ("category_assignments", "categories.json", "table_assignments"),
    )}
    source = documents["database.json"]["source"]
    manifest = {
        "package_format": PACKAGE_FORMAT, "package_version": "2.0",
        "package_readiness": "WARNING",
        "readiness_issues": ["Preflight has not been performed; activation is prohibited"],
        "generated_at": now.isoformat(),
        "source": source, "schema_fingerprint": fp,
        "counts": counts,
        "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest(),
                   "bytes": len(data)} for name, data in sorted(files.items())],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(f"{PACKAGE_ROOT_NAME}/manifest.json", _json_bytes(manifest))
        for name, data in sorted(files.items()):
            archive.writestr(f"{PACKAGE_ROOT_NAME}/{name}", data)
    content = buf.getvalue()
    # Reuse DQA's own hardened v2 ZIP reader/validator, not a parallel parser.
    validated = validate_catalog_package_bytes(content)
    if (validated.schema_fingerprint != fp or
            validated.package_readiness != "WARNING" or
            validated.activation_eligible):
        raise RuntimeError("invalid snapshot package activation boundary")
    return CandidateCatalogPackage(content=content, schema_fingerprint=fp)
