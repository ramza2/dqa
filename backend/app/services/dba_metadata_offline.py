"""M2-1D: untrusted, offline metadata-only Oracle export parser (NO DB or I/O).

The proposed file is NOT authenticated DBA evidence. A matching hash only
detects accidental/inconsistent content; it is not a signature or approval.
This never writes Snapshot revisions or makes a Catalog READY/active.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.adapters.schema_inspector.base import SchemaSnapshot
from app.services.schema_catalog_candidate import _fingerprint, _physical_payload, build_catalog_v2_candidate
from app.services.schema_snapshot_diff import compare_schema_snapshots
from app.services.schema_snapshot_history import _snapshot_from_payload

MAX_EXPORT_BYTES = 4_000_000
FORMAT = "dqa-offline-oracle-metadata-v1"
SOURCE = "oracle_demis_mock"
DATABASE = "FREEPDB1"
SCHEMA = "DEMIS_OWNER"
_IDENT = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_DATATYPE = re.compile(r"^[A-Z][A-Z0-9_ ()/.,+-]{0,95}$")
_GROUPS = (
    "tables", "columns", "primary_keys", "unique_constraints",
    "foreign_keys", "indexes",
)
_FIELD_RULES = {
    "tables": {
        "schema_name": "ident", "table_name": "ident",
        "table_type": "table_type", "table_comment": "comment?",
    },
    "columns": {
        "schema_name": "ident", "table_name": "ident",
        "ordinal_position": "ordinal", "column_name": "ident",
        "data_type": "datatype", "character_maximum_length": "number?",
        "numeric_precision": "number?", "numeric_scale": "signed?",
        "is_nullable": "bool", "default_value": "none",
        "column_comment": "comment?",
    },
    "primary_keys": {
        "schema_name": "ident", "table_name": "ident",
        "constraint_name": "ident", "column_name": "ident",
        "ordinal_position": "ordinal",
    },
    "unique_constraints": {
        "schema_name": "ident", "table_name": "ident",
        "constraint_name": "ident", "column_name": "ident",
        "ordinal_position": "ordinal",
    },
    "foreign_keys": {
        "schema_name": "ident", "constraint_name": "ident",
        "source_table": "ident", "target_schema": "ident",
        "target_table": "ident", "columns": "fk_members",
    },
    "indexes": {
        "schema_name": "ident", "table_name": "ident",
        "index_name": "ident", "is_unique": "bool",
        "index_method": "datatype?", "index_definition": "none",
        "columns": "index_members",
    },
}
_FK_MEMBER = {"ordinal_position": "ordinal", "source_column": "ident", "target_column": "ident"}
_INDEX_MEMBER = {"ordinal_position": "ordinal", "column_name": "ident"}


class OfflineMetadataError(ValueError):
    """Public stable reason only; never include untrusted metadata or rows."""


@dataclass(frozen=True)
class OfflinePreview:
    snapshot: SchemaSnapshot
    fingerprint: str
    candidate_zip: bytes
    source_name: str = SOURCE
    file_format: str = FORMAT
    preflight_verified: bool = False
    issuer_authenticated: bool = False
    activation_eligible: bool = False
    candidate_readiness: str = "WARNING"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for name, value in pairs:
        if name in result:
            raise OfflineMetadataError("DUPLICATE_JSON_KEY")
        result[name] = value
    return result


def _invalid_constant(_raw: str):
    raise OfflineMetadataError("INVALID_JSON_CONSTANT")


def _valid(rule: str, value: Any) -> bool:
    if rule == "none":
        return value is None
    if rule.endswith("?"):
        return value is None or _valid(rule[:-1], value)
    if rule == "ident":
        return isinstance(value, str) and _IDENT.fullmatch(value) is not None
    if rule == "comment":
        return isinstance(value, str) and len(value) <= 512 and "\x00" not in value
    if rule == "datatype":
        return isinstance(value, str) and _DATATYPE.fullmatch(value) is not None
    if rule == "table_type":
        return value == "BASE TABLE"
    if rule == "bool":
        return type(value) is bool
    if rule == "ordinal":
        return type(value) is int and 1 <= value <= 10_000
    if rule == "number":
        return type(value) is int and 0 <= value <= 1_000_000
    if rule == "signed":
        return type(value) is int and -127 <= value <= 1_000_000
    if rule in ("fk_members", "index_members"):
        expected = _FK_MEMBER if rule == "fk_members" else _INDEX_MEMBER
        return (
            isinstance(value, list) and 1 <= len(value) <= 100
            and all(_valid_object(member, expected) for member in value)
        )
    return False


def _valid_object(value: Any, spec: dict[str, str]) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == set(spec)
        and all(_valid(rule, value[key]) for key, rule in spec.items())
    )


def _validate_references(snapshot: SchemaSnapshot) -> None:
    tables = {(t.schema_name, t.table_name) for t in snapshot.tables}
    columns = {(c.schema_name, c.table_name, c.column_name) for c in snapshot.columns}
    if len(tables) != len(snapshot.tables) or len(columns) != len(snapshot.columns):
        raise OfflineMetadataError("DUPLICATE_OBJECT")
    if not tables or not columns:
        raise OfflineMetadataError("EMPTY_METADATA")
    for group in (snapshot.tables, snapshot.columns, snapshot.primary_keys,
                  snapshot.unique_constraints, snapshot.foreign_keys, snapshot.indexes):
        if any(record.schema_name != SCHEMA for record in group):
            raise OfflineMetadataError("SCHEMA_SCOPE_MISMATCH")
    if any((c.schema_name, c.table_name) not in tables for c in snapshot.columns):
        raise OfflineMetadataError("INVALID_REFERENCE")
    for keys in (snapshot.primary_keys, snapshot.unique_constraints):
        if any((item.schema_name, item.table_name, item.column_name) not in columns for item in keys):
            raise OfflineMetadataError("INVALID_REFERENCE")
    for ix in snapshot.indexes:
        if (ix.schema_name, ix.table_name) not in tables or any(
            (ix.schema_name, ix.table_name, c.column_name) not in columns for c in ix.columns
        ):
            raise OfflineMetadataError("INVALID_REFERENCE")
    for fk in snapshot.foreign_keys:
        if fk.target_schema != SCHEMA or (
            fk.schema_name, fk.source_table
        ) not in tables or (fk.target_schema, fk.target_table) not in tables:
            raise OfflineMetadataError("INVALID_REFERENCE")
        if any(
            (fk.schema_name, fk.source_table, col.source_column) not in columns
            or (fk.target_schema, fk.target_table, col.target_column) not in columns
            for col in fk.columns
        ):
            raise OfflineMetadataError("INVALID_REFERENCE")


def validate_offline_metadata_export(raw: bytes) -> OfflinePreview:
    """Parse one strictly-scoped synthetic Oracle export into an offline WARNING.

    Format is our own reference contract, not an assertion that a DBA produced
    or approved the bytes. No writes or arbitrary SQL are executed.
    """
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_EXPORT_BYTES:
        raise OfflineMetadataError("INVALID_EXPORT_SIZE")
    try:
        data = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys, parse_constant=_invalid_constant,
        )
    except OfflineMetadataError:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        raise OfflineMetadataError("INVALID_EXPORT_JSON") from None

    if not isinstance(data, dict) or set(data) != {
        "format", "source_name", "metadata_only", "claimed_fingerprint", "snapshot",
    }:
        raise OfflineMetadataError("INVALID_EXPORT_FIELDS")
    if (
        data["format"] != FORMAT
        or data["source_name"] != SOURCE
        or data["metadata_only"] is not True
        or not isinstance(data["claimed_fingerprint"], str)
        or _SHA256.fullmatch(data["claimed_fingerprint"]) is None
    ):
        raise OfflineMetadataError("INVALID_EXPORT_IDENTITY")
    body = data["snapshot"]
    if not isinstance(body, dict) or set(body) != {
        "snapshot_version", "db_type", "database_name", "schema_name", *_GROUPS,
    } or (
        type(body["snapshot_version"]) is not int or body["snapshot_version"] != 1
        or body["db_type"] != "oracle"
        or body["database_name"] != DATABASE or body["schema_name"] != SCHEMA
    ):
        raise OfflineMetadataError("INVALID_SNAPSHOT_IDENTITY")

    total = 0
    for group, spec in _FIELD_RULES.items():
        records = body[group]
        if not isinstance(records, list) or len(records) > 20_000:
            raise OfflineMetadataError("INVALID_METADATA_RECORDS")
        total += len(records)
        if total > 30_000 or any(not _valid_object(row, spec) for row in records):
            raise OfflineMetadataError("INVALID_METADATA_RECORDS")

    try:
        snapshot = _snapshot_from_payload(body)
        _validate_references(snapshot)
        compare_schema_snapshots(snapshot, snapshot)  # duplicate/group ordinal rules
        physical = _physical_payload(snapshot)
        fingerprint = _fingerprint(physical)
        if fingerprint != data["claimed_fingerprint"]:
            raise OfflineMetadataError("FINGERPRINT_MISMATCH")
        candidate_zip = build_catalog_v2_candidate(snapshot, source_name=SOURCE)
    except OfflineMetadataError:
        raise
    except (KeyError, ValueError, TypeError, AttributeError):
        raise OfflineMetadataError("INVALID_METADATA_STRUCTURE") from None

    return OfflinePreview(snapshot=snapshot, fingerprint=fingerprint, candidate_zip=candidate_zip)
