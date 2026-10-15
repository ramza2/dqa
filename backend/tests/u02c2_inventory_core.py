"""U-02-C-2: allowlisted, aggregate-only Legacy Catalog inventory.

Test-only module. Caller supplies a read-only SQLAlchemy Session and the
17 pinned Legacy ORM models. No credentials, host, freeform SQL, user data,
raw source/run ids, fingerprints or vectors are written to output.
"""
from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select

TABLES = (
    "catalog_source", "catalog_analysis_run", "catalog_analysis_snapshot",
    "catalog_table", "catalog_column",
    "catalog_key_constraint", "catalog_key_constraint_column",
    "catalog_relation", "catalog_relation_column",
    "catalog_index", "catalog_index_column",
    "catalog_category", "catalog_table_category",
    "catalog_preflight_result", "catalog_search_document",
    "catalog_embedding_run", "catalog_embedding",
)
DIRECT = frozenset({
    "catalog_analysis_run", "catalog_analysis_snapshot", "catalog_table",
    "catalog_relation", "catalog_category", "catalog_preflight_result",
    "catalog_search_document", "catalog_embedding_run",
})
VIA_TABLE = {
    "catalog_column": "table_id",
    "catalog_key_constraint": "table_id",
    "catalog_index": "table_id",
    "catalog_table_category": "table_id",
}
VERSION = 1
MAX_SOURCES = 20
MAX_RUNS_PER_SOURCE = 1000


class InventoryRejected(ValueError):
    """Closed failure; do not include row contents/identifiers in message."""


def validate_run_links(source_ids, runs, snapshots):
    """Pure strict Source→Run→Snapshot validation, preserving internal IDs only.

    runs: (run_id, source_id, status)
    snapshots: (snapshot_id, source_id, run_id)
    """
    known_sources = set(source_ids)
    run_index = {}
    for run_id, sid, status in runs:
        if sid not in known_sources or run_id in run_index:
            raise InventoryRejected("RUN_SOURCE_OR_DUPLICATE")
        if not isinstance(status, str) or not status.strip():
            raise InventoryRejected("RUN_STATUS_UNKNOWN")
        run_index[run_id] = (sid, status)

    snapshot_per_run = Counter()
    seen_snapshots = set()
    for snapshot_id, sid, run_id in snapshots:
        if (snapshot_id in seen_snapshots or sid not in known_sources
                or run_id not in run_index or run_index[run_id][0] != sid):
            raise InventoryRejected("SNAPSHOT_LINK_INVALID")
        seen_snapshots.add(snapshot_id)
        snapshot_per_run[run_id] += 1
        if snapshot_per_run[run_id] > 1:
            raise InventoryRejected("MULTIPLE_SNAPSHOTS_FOR_RUN")
        if run_index[run_id][1] != "SUCCESS":
            raise InventoryRejected("SNAPSHOT_RUN_NOT_SUCCESS")

    output = {}
    for sid in source_ids:
        source_runs = sorted(
            [(run_id, status) for run_id, (source_id, status) in run_index.items()
             if source_id == sid],
            key=lambda item: item[0],
        )
        status_counts = {
            "SUCCESS": sum(status == "SUCCESS" for _, status in source_runs),
            "FAILED": sum(status == "FAILED" for _, status in source_runs),
            "OTHER": sum(status not in {"SUCCESS", "FAILED"} for _, status in source_runs),
        }
        output[sid] = {
            "run_status_counts": status_counts,
            "run_evidence": [
                {
                    "run_alias": f"RUN_{number:04d}",
                    "status_class": status if status in {"SUCCESS", "FAILED"} else "OTHER",
                    "snapshot_present": snapshot_per_run.get(run_id, 0) == 1,
                    "dqa_snapshot_revision_id": None,
                    "dqa_import_revision_id": None,
                }
                for number, (run_id, status) in enumerate(source_runs, 1)
            ],
        }
    return output


def _count_scoped(session, models, table_name: str, source_id: int) -> int:
    model = models[table_name]
    stmt = select(func.count()).select_from(model)
    if table_name == "catalog_source":
        stmt = stmt.where(model.id == source_id)
    elif table_name in DIRECT:
        stmt = stmt.where(model.source_id == source_id)
    elif table_name in VIA_TABLE:
        table = models["catalog_table"]
        stmt = stmt.join(table, getattr(model, VIA_TABLE[table_name]) == table.id)
        stmt = stmt.where(table.source_id == source_id)
    elif table_name == "catalog_key_constraint_column":
        key = models["catalog_key_constraint"]
        table = models["catalog_table"]
        stmt = stmt.join(key, model.constraint_id == key.id)
        stmt = stmt.join(table, key.table_id == table.id).where(table.source_id == source_id)
    elif table_name == "catalog_relation_column":
        relation = models["catalog_relation"]
        stmt = stmt.join(relation, model.relation_id == relation.id)
        stmt = stmt.where(relation.source_id == source_id)
    elif table_name == "catalog_index_column":
        index = models["catalog_index"]
        table = models["catalog_table"]
        stmt = stmt.join(index, model.index_id == index.id)
        stmt = stmt.join(table, index.table_id == table.id).where(table.source_id == source_id)
    elif table_name == "catalog_embedding":
        document = models["catalog_search_document"]
        stmt = stmt.join(document, model.search_document_id == document.id)
        stmt = stmt.where(document.source_id == source_id)
    else:
        raise InventoryRejected("UNSUPPORTED_TABLE")
    result = session.scalar(stmt)
    if not isinstance(result, int) or result < 0:
        raise InventoryRejected("INVALID_COUNT")
    return result


def collect_inventory(session, models, selected_source_ids):
    """Count only the explicitly selected sources inside caller's READ ONLY TX.

    Source aliases intentionally cannot act as durable ID crosswalks.
    All actual identity binding, archival and DQA revisions remain UNRESOLVED.
    """
    if set(models) != set(TABLES):
        raise InventoryRejected("MODEL_ALLOWLIST_MISMATCH")
    source_ids = list(selected_source_ids)
    if (not source_ids or len(source_ids) > MAX_SOURCES
            or len(source_ids) != len(set(source_ids))
            or any(type(sid) is not int or sid <= 0 for sid in source_ids)):
        raise InventoryRejected("SOURCE_SELECTION_INVALID")
    source_ids = sorted(source_ids)
    runs = []
    snapshots = []
    for sid in source_ids:
        count = _count_scoped(session, models, "catalog_source", sid)
        if count != 1:
            raise InventoryRejected("SOURCE_NOT_FOUND")
        model = models["catalog_analysis_run"]
        result = session.execute(
            select(model.id, model.source_id, model.status)
            .where(model.source_id == sid).order_by(model.id)
            .limit(MAX_RUNS_PER_SOURCE + 1)
        ).all()
        if len(result) > MAX_RUNS_PER_SOURCE:
            raise InventoryRejected("RUN_LIMIT_EXCEEDED")
        runs.extend(tuple(r) for r in result)
        snapshot = models["catalog_analysis_snapshot"]
        snapshot_result = session.execute(
            select(snapshot.id, snapshot.source_id, snapshot.run_id)
            .where(snapshot.source_id == sid).order_by(snapshot.id)
            .limit(MAX_RUNS_PER_SOURCE + 1)
        ).all()
        if len(snapshot_result) > MAX_RUNS_PER_SOURCE:
            raise InventoryRejected("SNAPSHOT_LIMIT_EXCEEDED")
        snapshots.extend(tuple(r) for r in snapshot_result)

    crosswalk = validate_run_links(source_ids, runs, snapshots)
    sources = []
    for ordinal, sid in enumerate(source_ids, 1):
        counts = {table: _count_scoped(session, models, table, sid) for table in TABLES}
        if counts["catalog_analysis_run"] != len(crosswalk[sid]["run_evidence"]):
            raise InventoryRejected("RUN_COUNT_CHANGED_DURING_READ")
        if counts["catalog_analysis_snapshot"] != sum(
            r["snapshot_present"] for r in crosswalk[sid]["run_evidence"]
        ):
            raise InventoryRejected("SNAPSHOT_COUNT_CHANGED_DURING_READ")
        # A table/category assignment must not cross source identities.
        assignment = models["catalog_table_category"]
        table = models["catalog_table"]
        category = models["catalog_category"]
        matched = session.scalar(
            select(func.count()).select_from(assignment)
            .join(table, assignment.table_id == table.id)
            .join(category, assignment.category_id == category.id)
            .where(table.source_id == sid, category.source_id == sid)
        )
        if matched != counts["catalog_table_category"]:
            raise InventoryRejected("CROSS_SOURCE_CATEGORY")
        sources.append({
            "source_alias": f"SRC_{ordinal:03d}",
            "table_counts": counts,
            **crosswalk[sid],
            "source_to_dqa": {
                "dqa_source_name": None, "dqa_catalog_import_revision_id": None,
                "status": "UNRESOLVED_PENDING_APPROVAL",
            },
        })

    return {
        "schema_version": VERSION,
        "evidence_kind": "SYNTHETIC_ISOLATED_LEGACY_PG",
        "cutover_allowed": False,
        "role": "AGGREGATE_EVIDENCE_ONLY",
        "alias_policy": "EPHEMERAL_POSITIONAL_NOT_DURABLE_CROSSWALK",
        "table_count": len(TABLES),
        "sources": sources,
    }
