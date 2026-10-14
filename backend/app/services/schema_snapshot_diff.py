"""Deterministic, metadata-only comparison of two Oracle SchemaSnapshots.

Pure offline foundation: no DB I/O, no persistence, no review/approval, no
Catalog activation. Never infer 'no changes' without an explicit baseline.
Uses the identical canonical physical payload/fingerprint as Catalog v2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.adapters.schema_inspector.base import SchemaSnapshot
from app.services.schema_catalog_candidate import _fingerprint, _physical_payload


ObjectType = Literal[
    "TABLE", "COLUMN", "PRIMARY_KEY", "UNIQUE_CONSTRAINT",
    "FOREIGN_KEY", "INDEX",
]
ChangeType = Literal["ADDED", "REMOVED", "CHANGED"]


@dataclass(frozen=True)
class SnapshotChange:
    object_type: ObjectType
    change_type: ChangeType
    # Tuple identity avoids ambiguity for quoted identifiers containing dots.
    object_key: tuple[str, ...]
    # Never return before/after bodies, SQL definitions or default expressions.
    changed_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChangeCount:
    added: int = 0
    removed: int = 0
    changed: int = 0

    @property
    def total(self) -> int:
        return self.added + self.removed + self.changed


@dataclass(frozen=True)
class SnapshotDiff:
    db_type: str
    database_name: str
    schema_name: str
    base_fingerprint: str
    target_fingerprint: str
    identical: bool
    total_changes: int
    counts: dict[str, ChangeCount]
    changes: tuple[SnapshotChange, ...]


_FIELDS: tuple[tuple[ObjectType, str, tuple[str, ...]], ...] = (
    ("TABLE", "tables", ("schema_name", "table_name")),
    ("COLUMN", "columns", ("schema_name", "table_name", "column_name")),
    ("PRIMARY_KEY", "primary_keys", ("schema_name", "table_name", "constraint_name")),
    ("UNIQUE_CONSTRAINT", "unique_constraints", ("schema_name", "table_name", "constraint_name")),
    ("FOREIGN_KEY", "foreign_keys", ("schema_name", "source_table", "constraint_name")),
    ("INDEX", "indexes", ("schema_name", "table_name", "index_name")),
)
_GROUPED = frozenset(("PRIMARY_KEY", "UNIQUE_CONSTRAINT"))


def _key(record: dict[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
    result = tuple(record.get(field) for field in fields)
    if not all(isinstance(part, str) and part for part in result):
        raise ValueError("invalid SchemaSnapshot object identity")
    return result


def _index_records(
    records: list[dict[str, Any]],
    object_type: ObjectType,
    fields: tuple[str, ...],
) -> dict[tuple[str, ...], dict[str, Any]]:
    if object_type in _GROUPED:
        groups: dict[tuple[str, ...], list[tuple[int, str]]] = {}
        for record in records:
            identity = _key(record, fields)
            ordinal = record["ordinal_position"]
            column = record["column_name"]
            if not isinstance(ordinal, int) or ordinal < 1 or not isinstance(column, str) or not column:
                raise ValueError("invalid key constraint member")
            groups.setdefault(identity, []).append((ordinal, column))
        result = {}
        for identity, members in groups.items():
            if len(set(members)) != len(members) or len({position for position, _ in members}) != len(members):
                raise ValueError("duplicate key constraint member or ordinal")
            result[identity] = {"columns": tuple(sorted(members))}
        return result

    result: dict[tuple[str, ...], dict[str, Any]] = {}
    for raw in records:
        identity = _key(raw, fields)
        if identity in result:
            raise ValueError("duplicate SchemaSnapshot object identity")
        value = {k: v for k, v in raw.items() if k not in fields}
        # Rows are sorted by ordinal, not the adapter's fetch/order sequence.
        if object_type == "FOREIGN_KEY":
            value["columns"] = _ordered_columns(raw["columns"], "source_column", "target_column")
        elif object_type == "INDEX":
            value["columns"] = _ordered_columns(raw["columns"], "column_name")
        result[identity] = value
    return result


def _ordered_columns(members: list[dict[str, Any]] | tuple[dict[str, Any], ...], *names: str) -> tuple:
    ordered = []
    ordinals = set()
    for member in members:
        ordinal = member["ordinal_position"]
        if not isinstance(ordinal, int) or ordinal < 1 or ordinal in ordinals:
            raise ValueError("invalid or duplicate ordered column ordinal")
        ordinals.add(ordinal)
        values = tuple(member[field] for field in names)
        if not all(isinstance(value, str) and value for value in values):
            raise ValueError("invalid ordered column name")
        ordered.append((ordinal, *values))
    return tuple(sorted(ordered))


def compare_schema_snapshots(base: SchemaSnapshot, target: SchemaSnapshot) -> SnapshotDiff:
    """Compare two explicit same-target baselines. No baseline -> no comparison.

    Does not use the legacy Analyzer's (different-algorithm) fingerprint.
    Only DQA snapshot-to-snapshot SHA-256 fingerprints are comparable here.
    """
    if not isinstance(base, SchemaSnapshot) or not isinstance(target, SchemaSnapshot):
        raise TypeError("two SchemaSnapshot objects are required")
    identity = (base.db_type, base.database_name, base.schema_name)
    if not all(identity) or identity != (target.db_type, target.database_name, target.schema_name):
        raise ValueError("cross-target SchemaSnapshot comparison is prohibited")
    if base.db_type.casefold() != "oracle":
        raise ValueError("only Oracle SchemaSnapshots are supported")

    before = _physical_payload(base)
    after = _physical_payload(target)
    counts: dict[str, ChangeCount] = {}
    changes: list[SnapshotChange] = []

    for object_type, field, identity_fields in _FIELDS:
        left = _index_records(before[field], object_type, identity_fields)
        right = _index_records(after[field], object_type, identity_fields)
        added = sorted(right.keys() - left.keys())
        removed = sorted(left.keys() - right.keys())
        changed = []
        for key in sorted(left.keys() & right.keys()):
            changed_fields = tuple(sorted(
                prop for prop in left[key].keys() | right[key].keys()
                if left[key].get(prop) != right[key].get(prop)
            ))
            if changed_fields:
                changed.append((key, changed_fields))

        counts[object_type] = ChangeCount(
            added=len(added), removed=len(removed), changed=len(changed)
        )
        changes.extend(
            SnapshotChange(object_type, "ADDED", key) for key in added
        )
        changes.extend(
            SnapshotChange(object_type, "REMOVED", key) for key in removed
        )
        changes.extend(
            SnapshotChange(object_type, "CHANGED", key, fields)
            for key, fields in changed
        )

    total = sum(item.total for item in counts.values())
    base_fp = _fingerprint(before)
    target_fp = _fingerprint(after)
    if (base_fp == target_fp) != (total == 0):
        raise ValueError("fingerprint/diff inconsistency")
    return SnapshotDiff(
        db_type=base.db_type,
        database_name=base.database_name,
        schema_name=base.schema_name,
        base_fingerprint=base_fp,
        target_fingerprint=target_fp,
        identical=(total == 0),
        total_changes=total,
        counts=counts,
        changes=tuple(changes),
    )
