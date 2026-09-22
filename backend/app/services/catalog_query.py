"""Active Catalog metadata query: filter stored JSONB for the current active revision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.models.catalog_import import CatalogImportRevision
from app.repositories.catalog_active import CatalogActiveRepository
from app.repositories.catalog_import import CatalogImportRepository
from app.schemas.catalog_query import (
    CatalogCategoryAssignment,
    CatalogCategoryItem,
    CatalogColumnItem,
    CatalogIndexItem,
    CatalogRelationColumnMapping,
    CatalogRelationItem,
    CatalogTableDetail,
    CatalogTableItem,
)


@dataclass(frozen=True)
class ResolvedActiveRevision:
    """One request-scoped snapshot of the active Catalog import revision."""

    source_name: str
    revision_id: int
    schema_fingerprint: str
    revision: CatalogImportRevision


@dataclass(frozen=True)
class PageResult:
    items: list[Any]
    total: int
    limit: int
    offset: int


def resolve_active_revision(session: Session, source_name: str) -> ResolvedActiveRevision:
    """Resolve active pointer once; reuse the same revision for the whole request."""
    pointer = CatalogActiveRepository(session).get_active_by_source_name(source_name)
    if pointer is None:
        raise CatalogQueryError(
            CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND,
            "active catalog revision not found for source",
        )
    revision = CatalogImportRepository(session).get_by_id(pointer.catalog_import_revision_id)
    if revision is None:
        raise CatalogQueryError(
            CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND,
            "active catalog revision not found for source",
        )
    return ResolvedActiveRevision(
        source_name=revision.source_name,
        revision_id=revision.id,
        schema_fingerprint=revision.schema_fingerprint,
        revision=revision,
    )


def list_tables(
    session: Session,
    source_name: str,
    *,
    q: str | None = None,
    schema_name: str | None = None,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[ResolvedActiveRevision, PageResult]:
    resolved = resolve_active_revision(session, source_name)
    assignments = _table_category_index(resolved.revision.categories_json)
    items = [_map_table(raw, assignments) for raw in _doc_list(resolved.revision.tables_json, "tables")]

    filtered: list[CatalogTableItem] = []
    for item in items:
        if schema_name is not None and item.schema_name != schema_name:
            continue
        if category is not None and category not in item.category_ids:
            continue
        if q and not _matches_q(q, item.name, item.comment):
            continue
        filtered.append(item)

    filtered.sort(key=lambda t: (t.schema_name.casefold(), t.name.casefold()))
    return resolved, _paginate(filtered, limit=limit, offset=offset)


def get_table(
    session: Session,
    source_name: str,
    schema_name: str,
    table_name: str,
) -> tuple[ResolvedActiveRevision, CatalogTableDetail]:
    resolved = resolve_active_revision(session, source_name)
    assignments = _table_category_index(resolved.revision.categories_json)
    for raw in _doc_list(resolved.revision.tables_json, "tables"):
        item = _map_table(raw, assignments)
        if item.schema_name == schema_name and item.name == table_name:
            return resolved, CatalogTableDetail(**item.model_dump())
    raise CatalogQueryError(
        CatalogQueryErrorCode.TABLE_NOT_FOUND,
        "table not found in active catalog",
    )


def list_columns(
    session: Session,
    source_name: str,
    *,
    q: str | None = None,
    schema_name: str | None = None,
    table_name: str | None = None,
    is_primary_key: bool | None = None,
    is_unique: bool | None = None,
    nullable: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[ResolvedActiveRevision, PageResult]:
    resolved = resolve_active_revision(session, source_name)
    items = [_map_column(raw) for raw in _doc_list(resolved.revision.columns_json, "columns")]

    filtered: list[CatalogColumnItem] = []
    for item in items:
        if schema_name is not None and item.schema_name != schema_name:
            continue
        if table_name is not None and item.table_name != table_name:
            continue
        if is_primary_key is not None and item.is_primary_key is not is_primary_key:
            continue
        if is_unique is not None and item.is_unique is not is_unique:
            continue
        if nullable is not None and item.nullable is not nullable:
            continue
        if q and not _matches_q(q, item.name, item.comment):
            continue
        filtered.append(item)

    filtered.sort(
        key=lambda c: (
            (c.schema_name or "").casefold(),
            c.table_name.casefold(),
            c.ordinal if c.ordinal is not None else 10**9,
            c.name.casefold(),
        )
    )
    return resolved, _paginate(filtered, limit=limit, offset=offset)


def list_relations(
    session: Session,
    source_name: str,
    *,
    schema_name: str | None = None,
    table_name: str | None = None,
    referenced_table_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[ResolvedActiveRevision, PageResult]:
    resolved = resolve_active_revision(session, source_name)
    items = [_map_relation(raw) for raw in _doc_list(resolved.revision.relations_json, "relations")]

    filtered: list[CatalogRelationItem] = []
    for item in items:
        if schema_name is not None and item.schema_name != schema_name:
            continue
        if table_name is not None and item.table_name != table_name:
            continue
        if referenced_table_name is not None and item.referenced_table_name != referenced_table_name:
            continue
        filtered.append(item)

    filtered.sort(
        key=lambda r: (
            (r.schema_name or "").casefold(),
            r.table_name.casefold(),
            (r.name or "").casefold(),
        )
    )
    return resolved, _paginate(filtered, limit=limit, offset=offset)


def list_indexes(
    session: Session,
    source_name: str,
    *,
    schema_name: str | None = None,
    table_name: str | None = None,
    unique: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[ResolvedActiveRevision, PageResult]:
    resolved = resolve_active_revision(session, source_name)
    items = [_map_index(raw) for raw in _doc_list(resolved.revision.indexes_json, "indexes")]

    filtered: list[CatalogIndexItem] = []
    for item in items:
        if schema_name is not None and item.schema_name != schema_name:
            continue
        if table_name is not None and item.table_name != table_name:
            continue
        if unique is not None and item.unique is not unique:
            continue
        filtered.append(item)

    filtered.sort(
        key=lambda i: (
            (i.schema_name or "").casefold(),
            i.table_name.casefold(),
            i.name.casefold(),
        )
    )
    return resolved, _paginate(filtered, limit=limit, offset=offset)


def list_categories(
    session: Session,
    source_name: str,
    *,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[ResolvedActiveRevision, PageResult]:
    resolved = resolve_active_revision(session, source_name)
    categories_doc = resolved.revision.categories_json
    assignments_by_category = _assignments_by_category(categories_doc)
    items = [
        _map_category(raw, assignments_by_category)
        for raw in _doc_list(categories_doc, "categories")
    ]

    filtered: list[CatalogCategoryItem] = []
    for item in items:
        if q and not _matches_q(q, item.id, item.name, item.description):
            continue
        filtered.append(item)

    filtered.sort(key=lambda c: ((c.name or "").casefold(), c.id.casefold()))
    return resolved, _paginate(filtered, limit=limit, offset=offset)


def _paginate(items: list[Any], *, limit: int, offset: int) -> PageResult:
    total = len(items)
    return PageResult(items=items[offset : offset + limit], total=total, limit=limit, offset=offset)


def _doc_list(document: Any, key: str) -> list[dict[str, Any]]:
    if not isinstance(document, dict):
        return []
    value = document.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _split_table_key(value: Any) -> tuple[str | None, str | None]:
    """Parse producer `SCHEMA.TABLE` keys (Oracle-style). Invalid values → (None, None)."""
    if not isinstance(value, str):
        return None, None
    text = value.strip()
    if "." not in text:
        return None, None
    schema, table = text.rsplit(".", 1)
    schema = schema.strip()
    table = table.strip()
    if not schema or not table:
        return None, None
    return schema, table


def _comment_from(raw: dict[str, Any]) -> str | None:
    for key in ("table_comment", "column_comment", "comment", "description", "db_comment"):
        if key in raw and raw[key] is not None:
            return _text(raw[key])
    return None


def _bool_from(raw: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"true", "y", "yes", "1"}:
                return True
            if lowered in {"false", "n", "no", "0"}:
                return False
    return None


def _int_from(raw: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value.strip())
    return None


def _confidence_from(raw: dict[str, Any]) -> float | int | str | None:
    if "confidence" not in raw:
        return None
    value = raw.get("confidence")
    if value is None or isinstance(value, (int, float, str)):
        return value
    return None


def _matches_q(q: str, *candidates: str | None) -> bool:
    needle = q.casefold()
    for candidate in candidates:
        if candidate is not None and needle in candidate.casefold():
            return True
    return False


def _lookup_key(schema: str | None, table: str) -> tuple[str, str]:
    return ((schema or "").casefold(), table.casefold())


def _assignment_schema_table(raw: dict[str, Any]) -> tuple[str | None, str | None]:
    schema, table = _split_table_key(raw.get("table_key"))
    if table:
        return schema, table
    table = _text(raw.get("table") or raw.get("table_name"))
    schema = _text(raw.get("schema") or raw.get("schema_name"))
    return schema, table


def _assignment_category_id(raw: dict[str, Any]) -> str | None:
    return _text(
        raw.get("category_key")
        or raw.get("category_id")
        or raw.get("category")
        or raw.get("id")
    )


def _table_category_index(categories_doc: Any) -> dict[tuple[str, str], list[str]]:
    index: dict[tuple[str, str], list[str]] = {}
    if not isinstance(categories_doc, dict):
        return index
    assignments = categories_doc.get("table_assignments")
    if not isinstance(assignments, list):
        return index
    for raw in assignments:
        if not isinstance(raw, dict):
            continue
        schema, table = _assignment_schema_table(raw)
        category_id = _assignment_category_id(raw)
        if not table or not category_id:
            continue
        key = _lookup_key(schema, table)
        index.setdefault(key, []).append(category_id)
    return index


def _assignments_by_category(
    categories_doc: Any,
) -> dict[str, list[CatalogCategoryAssignment]]:
    result: dict[str, list[CatalogCategoryAssignment]] = {}
    if not isinstance(categories_doc, dict):
        return result
    assignments = categories_doc.get("table_assignments")
    if not isinstance(assignments, list):
        return result
    for raw in assignments:
        if not isinstance(raw, dict):
            continue
        schema, table = _assignment_schema_table(raw)
        category_id = _assignment_category_id(raw)
        if not table or not category_id:
            continue
        result.setdefault(category_id, []).append(
            CatalogCategoryAssignment(
                schema_name=schema,
                table_name=table,
                provenance=_text(
                    raw.get("assignment_source")
                    or raw.get("provenance")
                    or raw.get("source")
                ),
                is_primary=_bool_from(raw, "is_primary"),
                confidence=_confidence_from(raw),
                note=_text(raw.get("note")),
            )
        )
    return result


def _map_table(
    raw: dict[str, Any],
    assignments: dict[tuple[str, str], list[str]],
) -> CatalogTableItem:
    schema_from_key, table_from_key = _split_table_key(raw.get("table_key"))
    schema = _text(raw.get("schema_name") or raw.get("schema")) or schema_from_key or ""
    name = (
        _text(raw.get("table_name") or raw.get("name") or raw.get("table"))
        or table_from_key
        or ""
    )
    category_ids: list[str] = []
    raw_categories = raw.get("categories") or raw.get("category_ids")
    if isinstance(raw_categories, list):
        category_ids.extend(_text(c) for c in raw_categories if _text(c))
    category_ids.extend(assignments.get(_lookup_key(schema, name), []))
    seen: set[str] = set()
    unique_ids: list[str] = []
    for cid in category_ids:
        if cid not in seen:
            seen.add(cid)
            unique_ids.append(cid)
    return CatalogTableItem(
        schema_name=schema,
        name=name,
        comment=_comment_from(raw),
        table_type=_text(raw.get("table_type") or raw.get("type")),
        category_ids=unique_ids,
    )


def _map_column(raw: dict[str, Any]) -> CatalogColumnItem:
    schema_from_key, table_from_key = _split_table_key(raw.get("table_key"))
    return CatalogColumnItem(
        schema_name=_text(raw.get("schema_name") or raw.get("schema")) or schema_from_key,
        table_name=_text(raw.get("table_name") or raw.get("table")) or table_from_key or "",
        name=_text(raw.get("column_name") or raw.get("name") or raw.get("column")) or "",
        ordinal=_int_from(raw, "ordinal_position", "ordinal", "position"),
        data_type=_text(raw.get("data_type") or raw.get("type")),
        comment=_comment_from(raw),
        nullable=_bool_from(raw, "nullable", "is_nullable"),
        is_primary_key=_bool_from(raw, "primary_key", "is_primary_key", "pk"),
        is_unique=_bool_from(raw, "unique", "is_unique"),
        default=_text(raw.get("default_value") or raw.get("default")),
    )


def _map_relation(raw: dict[str, Any]) -> CatalogRelationItem:
    source_schema, source_table = _split_table_key(raw.get("source_table_key"))
    target_schema, target_table = _split_table_key(raw.get("target_table_key"))

    columns: list[CatalogRelationColumnMapping] = []
    raw_columns = (
        raw.get("column_mapping")
        or raw.get("columns")
        or raw.get("column_mappings")
        or raw.get("mappings")
    )
    mapping_entries: list[tuple[int, CatalogRelationColumnMapping]] = []
    if isinstance(raw_columns, list):
        for index, entry in enumerate(raw_columns):
            if not isinstance(entry, dict):
                continue
            col = _text(
                entry.get("source_column")
                or entry.get("column")
                or entry.get("from")
            )
            ref = _text(
                entry.get("target_column")
                or entry.get("referenced_column")
                or entry.get("to")
            )
            if not col or not ref:
                continue
            ordinal = _int_from(entry, "ordinal_position", "ordinal", "position")
            mapping_entries.append(
                (
                    ordinal if ordinal is not None else index,
                    CatalogRelationColumnMapping(column=col, referenced_column=ref),
                )
            )
    mapping_entries.sort(key=lambda item: item[0])
    columns = [item[1] for item in mapping_entries]

    return CatalogRelationItem(
        name=_text(raw.get("constraint_name") or raw.get("name")),
        schema_name=_text(
            raw.get("schema_name") or raw.get("schema") or raw.get("source_schema")
        )
        or source_schema,
        table_name=_text(raw.get("table_name") or raw.get("table") or raw.get("source_table"))
        or source_table
        or "",
        referenced_schema_name=_text(
            raw.get("referenced_schema")
            or raw.get("referenced_schema_name")
            or raw.get("target_schema")
        )
        or target_schema,
        referenced_table_name=_text(
            raw.get("referenced_table")
            or raw.get("referenced_table_name")
            or raw.get("target_table")
        )
        or target_table
        or "",
        columns=columns,
    )


def _map_index(raw: dict[str, Any]) -> CatalogIndexItem:
    schema_from_key, table_from_key = _split_table_key(raw.get("table_key"))
    columns: list[str] = []
    raw_columns = raw.get("columns") or raw.get("column_names")
    if isinstance(raw_columns, list):
        for entry in raw_columns:
            if isinstance(entry, str):
                columns.append(entry)
            elif isinstance(entry, dict):
                name = _text(entry.get("column") or entry.get("name") or entry.get("column_name"))
                if name:
                    columns.append(name)
    return CatalogIndexItem(
        name=_text(raw.get("index_name") or raw.get("name")) or "",
        schema_name=_text(raw.get("schema_name") or raw.get("schema")) or schema_from_key,
        table_name=_text(raw.get("table_name") or raw.get("table")) or table_from_key or "",
        unique=_bool_from(raw, "unique", "is_unique"),
        columns=columns,
        method=_text(raw.get("index_method") or raw.get("method") or raw.get("index_type") or raw.get("type")),
    )


def _map_category(
    raw: dict[str, Any],
    assignments_by_category: dict[str, list[CatalogCategoryAssignment]],
) -> CatalogCategoryItem:
    category_id = _text(raw.get("category_key") or raw.get("id") or raw.get("category_id")) or ""
    return CatalogCategoryItem(
        id=category_id,
        name=_text(raw.get("category_name") or raw.get("name") or raw.get("label")),
        description=_comment_from(raw),
        assignments=list(assignments_by_category.get(category_id, [])),
    )


__all__ = [
    "PageResult",
    "ResolvedActiveRevision",
    "get_table",
    "list_categories",
    "list_columns",
    "list_indexes",
    "list_relations",
    "list_tables",
    "resolve_active_revision",
]
