"""Safe table-centered ERD projection from a stored, *unapproved* Snapshot.

Read-only and source-bound; does not expose snapshot_json/default SQL, promote
Catalog READY, or connect to Oracle/DEMIS. All entries come from verified v1
physical metadata. This is NOT independent DBA preflight.
"""
from __future__ import annotations

from app.models.schema_snapshot_revision import SchemaSnapshotRevision
from app.services.schema_catalog_candidate import _fingerprint, _physical_payload
from app.services.schema_snapshot_diff import compare_schema_snapshots
from app.services.schema_snapshot_history import _snapshot_from_payload

_MAX_EDGES = 40


class SnapshotErdError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def build_snapshot_erd(
    row: SchemaSnapshotRevision, *, query: str | None = None,
    offset: int = 0, limit: int = 30,
    focus_schema: str | None = None, focus_table: str | None = None,
) -> dict:
    """Return a bounded, allowlisted projection; never the raw stored JSON."""
    if (focus_schema is None) != (focus_table is None):
        raise SnapshotErdError("SNAPSHOT_ERD_INVALID_FOCUS")
    try:
        if row.snapshot_version != 1:
            raise ValueError("unsupported version")
        snapshot = _snapshot_from_payload(row.snapshot_json)
        if (
            (snapshot.db_type, snapshot.database_name, snapshot.schema_name)
            != (row.db_type, row.database_name, row.schema_name)
        ):
            raise ValueError("target identity mismatch")
        compare_schema_snapshots(snapshot, snapshot)
        if _fingerprint(_physical_payload(snapshot)) != row.schema_fingerprint:
            raise ValueError("fingerprint mismatch")
        if row.counts_json != {
            "tables": len(snapshot.tables),
            "columns": len(snapshot.columns),
            "primary_key_columns": len(snapshot.primary_keys),
            "unique_key_columns": len(snapshot.unique_constraints),
            "foreign_keys": len(snapshot.foreign_keys),
            "indexes": len(snapshot.indexes),
        }:
            raise ValueError("counts mismatch")
    except Exception:
        raise SnapshotErdError("SNAPSHOT_ERD_UNVERIFIABLE") from None

    tables = sorted(
        ((t.schema_name, t.table_name) for t in snapshot.tables),
        key=lambda x: x,
    )
    table_set = set(tables)
    if focus_schema is not None and (focus_schema, focus_table) not in table_set:
        raise SnapshotErdError("SNAPSHOT_ERD_TABLE_NOT_FOUND")

    needle = (query or "").strip().casefold()
    filtered = [name for name in tables
                if not needle or needle in (name[0] + "." + name[1]).casefold()]
    visible_tables = [
        {"schema_name": schema, "table_name": table}
        for schema, table in filtered[offset:offset + limit]
    ]

    edges = []
    if focus_schema is not None:
        for fk in snapshot.foreign_keys:
            if not (
                (fk.schema_name == focus_schema and fk.source_table == focus_table)
                or (fk.target_schema == focus_schema and fk.target_table == focus_table)
            ):
                continue
            # The real FK direction is preserved, even for cross-schema references.
            is_out = fk.schema_name == focus_schema and fk.source_table == focus_table
            other = (
                (fk.target_schema, fk.target_table) if is_out
                else (fk.schema_name, fk.source_table)
            )
            edges.append({
                "direction": "OUT" if is_out else "IN",
                "constraint_name": fk.constraint_name,
                "source_schema": fk.schema_name,
                "source_table": fk.source_table,
                "target_schema": fk.target_schema,
                "target_table": fk.target_table,
                "referenced_only": other not in table_set,
                "column_mapping": [
                    {"source": c.source_column, "target": c.target_column}
                    for c in sorted(fk.columns, key=lambda c: c.ordinal_position)
                ],
            })
        edges.sort(key=lambda e: (
            e["direction"], e["source_schema"], e["source_table"],
            e["target_schema"], e["target_table"], e["constraint_name"],
        ))

    return {
        "source_name": row.source_name,
        "revision_id": row.id,
        "schema_fingerprint": row.schema_fingerprint,
        "preflight_status": "NOT_VERIFIED",
        "activation_eligible": False,
        "total_tables": len(filtered),
        "offset": offset,
        "limit": limit,
        "tables": visible_tables,
        "focus_schema": focus_schema,
        "focus_table": focus_table,
        "total_edges": len(edges),
        "edges_truncated": len(edges) > _MAX_EDGES,
        "edges": edges[:_MAX_EDGES],
    }
