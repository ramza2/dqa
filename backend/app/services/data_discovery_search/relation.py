"""FK relation expansion over Active Catalog relations_json (BFS)."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from app.models.catalog_import import CatalogImportRevision
from app.services.catalog_query import _doc_list, _map_relation


@dataclass(frozen=True)
class RelationHop:
    from_schema: str
    from_table: str
    to_schema: str
    to_table: str
    constraint_name: str | None
    direction: str
    from_columns: tuple[str, ...]
    to_columns: tuple[str, ...]


@dataclass(frozen=True)
class RelatedTable:
    schema_name: str
    table_name: str
    hop_distance: int
    seed_schema: str
    seed_table: str
    path: tuple[RelationHop, ...]


def expand_relations(
    revision: CatalogImportRevision,
    *,
    seed_tables: list[tuple[str, str]],
    max_hops: int,
    max_seeds: int = 20,
) -> list[RelatedTable]:
    """Bidirectional BFS over (schema, table) nodes. Cycle-safe."""
    if max_hops <= 0 or not seed_tables:
        return []

    adjacency = _build_adjacency(revision)
    seeds = []
    seen_seeds: set[tuple[str, str]] = set()
    for schema, table in seed_tables:
        key = (schema, table)
        if not schema or not table or key in seen_seeds:
            continue
        seen_seeds.add(key)
        seeds.append(key)
        if len(seeds) >= max_seeds:
            break

    related: dict[tuple[str, str], RelatedTable] = {}
    for seed in seeds:
        _bfs(seed, adjacency=adjacency, max_hops=max_hops, related=related)

    return sorted(
        related.values(),
        key=lambda item: (
            item.hop_distance,
            item.schema_name,
            item.table_name,
            item.seed_schema,
            item.seed_table,
        ),
    )


def _build_adjacency(
    revision: CatalogImportRevision,
) -> dict[tuple[str, str], list[RelationHop]]:
    adjacency: dict[tuple[str, str], list[RelationHop]] = {}
    for raw in _doc_list(revision.relations_json, "relations"):
        rel = _map_relation(raw)
        from_schema = rel.schema_name or ""
        to_schema = rel.referenced_schema_name or ""
        if not from_schema or not rel.table_name or not to_schema or not rel.referenced_table_name:
            continue
        from_cols = tuple(m.column for m in rel.columns)
        to_cols = tuple(m.referenced_column for m in rel.columns)
        forward = RelationHop(
            from_schema=from_schema,
            from_table=rel.table_name,
            to_schema=to_schema,
            to_table=rel.referenced_table_name,
            constraint_name=rel.name,
            direction="outbound",
            from_columns=from_cols,
            to_columns=to_cols,
        )
        backward = RelationHop(
            from_schema=to_schema,
            from_table=rel.referenced_table_name,
            to_schema=from_schema,
            to_table=rel.table_name,
            constraint_name=rel.name,
            direction="inbound",
            from_columns=to_cols,
            to_columns=from_cols,
        )
        adjacency.setdefault((from_schema, rel.table_name), []).append(forward)
        adjacency.setdefault((to_schema, rel.referenced_table_name), []).append(backward)

    for key in adjacency:
        adjacency[key] = sorted(
            adjacency[key],
            key=lambda hop: (
                hop.direction,
                hop.to_schema,
                hop.to_table,
                hop.constraint_name or "",
                hop.from_columns,
                hop.to_columns,
            ),
        )
    return adjacency


def _bfs(
    seed: tuple[str, str],
    *,
    adjacency: dict[tuple[str, str], list[RelationHop]],
    max_hops: int,
    related: dict[tuple[str, str], RelatedTable],
) -> None:
    queue: deque[tuple[tuple[str, str], int, tuple[RelationHop, ...]]] = deque(
        [(seed, 0, ())]
    )
    visited: set[tuple[str, str]] = {seed}

    while queue:
        node, distance, path = queue.popleft()
        if distance >= max_hops:
            continue
        for hop in adjacency.get(node, []):
            nxt = (hop.to_schema, hop.to_table)
            if nxt in visited:
                continue
            visited.add(nxt)
            new_path = path + (hop,)
            new_distance = distance + 1
            existing = related.get(nxt)
            if existing is None or new_distance < existing.hop_distance:
                related[nxt] = RelatedTable(
                    schema_name=nxt[0],
                    table_name=nxt[1],
                    hop_distance=new_distance,
                    seed_schema=seed[0],
                    seed_table=seed[1],
                    path=new_path,
                )
            queue.append((nxt, new_distance, new_path))
