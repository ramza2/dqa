"""Deterministic Data Discovery search-document builder and rebuild service.

Reads CatalogImportRevision JSON only. Never connects to DEMIS, never resolves
credentials, never calls embedding/LLM APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import (
    CatalogActivationError,
    CatalogActivationErrorCode,
)
from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.domain.data_discovery import (
    BUILDER_VERSION,
    DiscoveryIdentityKind,
    DiscoveryObjectType,
    SearchDocumentDraft,
    canonical_digest,
    document_fingerprint_for,
    physical_document_key,
)
from app.models.catalog_import import CatalogImportRevision
from app.models.data_discovery import DataDiscoveryDocument
from app.repositories.catalog_active import CatalogActiveRepository
from app.repositories.catalog_import import CatalogImportRepository
from app.repositories.data_discovery import DataDiscoveryRepository
from app.services.catalog_query import (
    _assignments_by_category,
    _doc_list,
    _map_category,
    _map_column,
    _map_index,
    _map_relation,
    _map_table,
    _table_category_index,
)


@dataclass(frozen=True)
class RebuildResult:
    catalog_import_revision_id: int
    source_name: str
    schema_fingerprint: str
    document_count: int
    upserted_count: int
    deleted_count: int
    builder_version: str


def build_documents_for_revision(revision: CatalogImportRevision) -> list[SearchDocumentDraft]:
    """Build deterministic TABLE/COLUMN documents from one import revision."""
    assignments = _table_category_index(revision.categories_json)
    tables = [
        _map_table(raw, assignments)
        for raw in _doc_list(revision.tables_json, "tables")
    ]
    columns = [_map_column(raw) for raw in _doc_list(revision.columns_json, "columns")]
    relations = [
        _map_relation(raw) for raw in _doc_list(revision.relations_json, "relations")
    ]
    indexes = [_map_index(raw) for raw in _doc_list(revision.indexes_json, "indexes")]
    categories_by_id = {
        item.id: item
        for item in (
            _map_category(raw, _assignments_by_category(revision.categories_json))
            for raw in _doc_list(revision.categories_json, "categories")
        )
        if item.id
    }

    tables_sorted = sorted(
        [t for t in tables if t.schema_name and t.name],
        key=lambda t: (t.schema_name, t.name),
    )
    columns_sorted = sorted(
        [c for c in columns if (c.schema_name or "") and c.table_name and c.name],
        key=lambda c: (
            c.schema_name or "",
            c.table_name,
            c.ordinal if c.ordinal is not None else 10**9,
            c.name,
        ),
    )

    columns_by_table: dict[tuple[str, str], list[Any]] = {}
    for col in columns_sorted:
        key = (col.schema_name or "", col.table_name)
        columns_by_table.setdefault(key, []).append(col)

    indexes_by_table: dict[tuple[str, str], list[Any]] = {}
    for idx in sorted(
        indexes,
        key=lambda i: ((i.schema_name or ""), i.table_name, i.name),
    ):
        key = (idx.schema_name or "", idx.table_name)
        indexes_by_table.setdefault(key, []).append(idx)

    outbound_by_table: dict[tuple[str, str], list[Any]] = {}
    inbound_by_column: dict[tuple[str, str, str], list[Any]] = {}
    for rel in sorted(
        relations,
        key=lambda r: (
            (r.schema_name or ""),
            r.table_name,
            (r.name or ""),
            (r.referenced_schema_name or ""),
            r.referenced_table_name,
        ),
    ):
        src_key = (rel.schema_name or "", rel.table_name)
        outbound_by_table.setdefault(src_key, []).append(rel)
        for mapping in rel.columns:
            col_key = (rel.schema_name or "", rel.table_name, mapping.column)
            inbound_by_column.setdefault(col_key, []).append(rel)

    table_comment_by_key = {
        (t.schema_name, t.name): t.comment for t in tables_sorted
    }

    drafts: list[SearchDocumentDraft] = []

    for table in tables_sorted:
        table_key = (table.schema_name, table.name)
        table_cols = columns_by_table.get(table_key, [])
        table_indexes = indexes_by_table.get(table_key, [])
        table_rels = outbound_by_table.get(table_key, [])
        category_lines = _category_lines(table.category_ids, categories_by_id)

        pk_names = sorted(
            {c.name for c in table_cols if c.is_primary_key},
            key=lambda n: n,
        )
        unique_cols = sorted(
            {c.name for c in table_cols if c.is_unique and not c.is_primary_key},
            key=lambda n: n,
        )

        lines: list[str] = [
            "Object Type: TABLE",
            f"Schema: {table.schema_name}",
            f"Table: {table.name}",
        ]
        if table.comment:
            lines.append(f"Table Comment: {table.comment}")
        if table.table_type:
            lines.append(f"Table Type: {table.table_type}")
        if table_cols:
            lines.append("Columns:")
            for col in table_cols:
                comment_part = f" — {col.comment}" if col.comment else ""
                type_part = f" ({col.data_type})" if col.data_type else ""
                lines.append(f"- {col.name}{type_part}{comment_part}")
        if pk_names:
            lines.append("Primary Keys: " + ", ".join(pk_names))
        if unique_cols:
            lines.append("Unique Columns: " + ", ".join(unique_cols))
        if table_indexes:
            lines.append("Indexes:")
            for idx in table_indexes:
                uniq = "unique" if idx.unique else "non-unique"
                cols = ", ".join(idx.columns) if idx.columns else ""
                method = f" [{idx.method}]" if idx.method else ""
                col_part = f": {cols}" if cols else ""
                lines.append(f"- {idx.name} ({uniq}){method}{col_part}")
        if table_rels:
            lines.append("Outbound Foreign Keys:")
            for rel in table_rels:
                ref_schema = rel.referenced_schema_name or ""
                ref_table = rel.referenced_table_name
                ref = f"{ref_schema}.{ref_table}" if ref_schema else ref_table
                mapping = ", ".join(
                    f"{m.column}->{m.referenced_column}" for m in rel.columns
                )
                name = rel.name or "(unnamed)"
                map_part = f" [{mapping}]" if mapping else ""
                lines.append(f"- {name}: {ref}{map_part}")
        if category_lines:
            lines.append("Categories:")
            lines.extend(category_lines)

        searchable_text = "\n".join(lines)
        document_key = physical_document_key(
            DiscoveryObjectType.TABLE,
            schema_name=table.schema_name,
            table_name=table.name,
        )
        source_fp = _table_source_fingerprint(
            table=table,
            columns=table_cols,
            indexes=table_indexes,
            relations=table_rels,
            category_lines=category_lines,
        )
        drafts.append(
            SearchDocumentDraft(
                document_key=document_key,
                object_type=DiscoveryObjectType.TABLE,
                identity_kind=DiscoveryIdentityKind.PHYSICAL,
                source_name=revision.source_name,
                catalog_revision_id=revision.id,
                schema_fingerprint=revision.schema_fingerprint,
                schema_name=table.schema_name,
                table_name=table.name,
                column_name=None,
                searchable_text=searchable_text,
                source_fingerprint=source_fp,
                document_fingerprint=document_fingerprint_for(
                    document_key=document_key,
                    searchable_text=searchable_text,
                    builder_version=BUILDER_VERSION,
                ),
                builder_version=BUILDER_VERSION,
            )
        )

    for col in columns_sorted:
        schema_name = col.schema_name or ""
        table_comment = table_comment_by_key.get((schema_name, col.table_name))
        col_rels = inbound_by_column.get((schema_name, col.table_name, col.name), [])

        lines = [
            "Object Type: COLUMN",
            f"Schema: {schema_name}",
            f"Table: {col.table_name}",
        ]
        if table_comment:
            lines.append(f"Table Comment: {table_comment}")
        lines.append(f"Column: {col.name}")
        if col.comment:
            lines.append(f"Column Comment: {col.comment}")
        if col.data_type:
            lines.append(f"Data Type: {col.data_type}")
        if col.nullable is not None:
            lines.append(f"Nullable: {'true' if col.nullable else 'false'}")
        if col.is_primary_key is not None:
            lines.append(f"Primary Key: {'true' if col.is_primary_key else 'false'}")
        if col.is_unique is not None:
            lines.append(f"Unique: {'true' if col.is_unique else 'false'}")
        if col_rels:
            lines.append("Foreign Keys:")
            for rel in col_rels:
                ref_schema = rel.referenced_schema_name or ""
                ref_table = rel.referenced_table_name
                ref = f"{ref_schema}.{ref_table}" if ref_schema else ref_table
                mapped = next(
                    (m for m in rel.columns if m.column == col.name),
                    None,
                )
                ref_col = mapped.referenced_column if mapped else ""
                name = rel.name or "(unnamed)"
                target = f"{ref}.{ref_col}" if ref_col else ref
                lines.append(f"- {name}: {col.name} -> {target}")

        searchable_text = "\n".join(lines)
        document_key = physical_document_key(
            DiscoveryObjectType.COLUMN,
            schema_name=schema_name,
            table_name=col.table_name,
            column_name=col.name,
        )
        source_fp = _column_source_fingerprint(
            schema_name=schema_name,
            column=col,
            table_comment=table_comment,
            relations=col_rels,
        )
        drafts.append(
            SearchDocumentDraft(
                document_key=document_key,
                object_type=DiscoveryObjectType.COLUMN,
                identity_kind=DiscoveryIdentityKind.PHYSICAL,
                source_name=revision.source_name,
                catalog_revision_id=revision.id,
                schema_fingerprint=revision.schema_fingerprint,
                schema_name=schema_name,
                table_name=col.table_name,
                column_name=col.name,
                searchable_text=searchable_text,
                source_fingerprint=source_fp,
                document_fingerprint=document_fingerprint_for(
                    document_key=document_key,
                    searchable_text=searchable_text,
                    builder_version=BUILDER_VERSION,
                ),
                builder_version=BUILDER_VERSION,
            )
        )

    drafts.sort(key=lambda d: d.document_key)
    return drafts


def rebuild_for_revision(session: Session, revision_id: int) -> RebuildResult:
    """Authoritative rebuild of derived documents for one Catalog revision.

    Other revisions are untouched. Caller owns the transaction/commit.
    """
    revision = CatalogImportRepository(session).get_by_id(revision_id)
    if revision is None:
        raise CatalogActivationError(
            CatalogActivationErrorCode.IMPORT_NOT_FOUND,
            "import revision not found",
        )

    drafts = build_documents_for_revision(revision)
    repo = DataDiscoveryRepository(session)
    reconcile = repo.reconcile_for_revision(
        revision.id,
        [_draft_to_model(draft) for draft in drafts],
    )
    return RebuildResult(
        catalog_import_revision_id=revision.id,
        source_name=revision.source_name,
        schema_fingerprint=revision.schema_fingerprint,
        document_count=len(drafts),
        upserted_count=reconcile.upserted_count,
        deleted_count=reconcile.deleted_count,
        builder_version=BUILDER_VERSION,
    )


def rebuild_for_active_source(session: Session, source_name: str) -> RebuildResult:
    """Rebuild documents for the currently active revision of ``source_name`` only."""
    pointer = CatalogActiveRepository(session).get_active_by_source_name(source_name)
    if pointer is None:
        raise CatalogQueryError(
            CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND,
            "active catalog revision not found for source",
        )
    return rebuild_for_revision(session, pointer.catalog_import_revision_id)


def _draft_to_model(draft: SearchDocumentDraft) -> DataDiscoveryDocument:
    return DataDiscoveryDocument(
        catalog_import_revision_id=draft.catalog_revision_id,
        source_name=draft.source_name,
        schema_fingerprint=draft.schema_fingerprint,
        object_type=draft.object_type.value,
        identity_kind=draft.identity_kind.value,
        schema_name=draft.schema_name,
        table_name=draft.table_name,
        column_name=draft.column_name,
        document_key=draft.document_key,
        searchable_text=draft.searchable_text,
        source_fingerprint=draft.source_fingerprint,
        document_fingerprint=draft.document_fingerprint,
        builder_version=draft.builder_version,
    )


def _category_lines(
    category_ids: list[str],
    categories_by_id: dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    for cid in sorted(set(category_ids)):
        cat = categories_by_id.get(cid)
        if cat is None:
            lines.append(f"- {cid}")
            continue
        name = cat.name or cid
        if cat.description:
            lines.append(f"- {cid}: {name} — {cat.description}")
        else:
            lines.append(f"- {cid}: {name}")
    return lines


def _table_source_fingerprint(
    *,
    table: Any,
    columns: list[Any],
    indexes: list[Any],
    relations: list[Any],
    category_lines: list[str],
) -> str:
    return canonical_digest(
        {
            "object_type": "TABLE",
            "schema_name": table.schema_name,
            "table_name": table.name,
            "comment": table.comment,
            "table_type": table.table_type,
            "columns": [
                {
                    "name": c.name,
                    "data_type": c.data_type,
                    "comment": c.comment,
                    "nullable": c.nullable,
                    "is_primary_key": c.is_primary_key,
                    "is_unique": c.is_unique,
                    "ordinal": c.ordinal,
                }
                for c in columns
            ],
            "indexes": [
                {
                    "name": i.name,
                    "unique": i.unique,
                    "columns": list(i.columns),
                    "method": i.method,
                }
                for i in indexes
            ],
            "outbound_relations": [
                {
                    "name": r.name,
                    "referenced_schema_name": r.referenced_schema_name,
                    "referenced_table_name": r.referenced_table_name,
                    "columns": [
                        {
                            "column": m.column,
                            "referenced_column": m.referenced_column,
                        }
                        for m in r.columns
                    ],
                }
                for r in relations
            ],
            "categories": category_lines,
        }
    )


def _column_source_fingerprint(
    *,
    schema_name: str,
    column: Any,
    table_comment: str | None,
    relations: list[Any],
) -> str:
    return canonical_digest(
        {
            "object_type": "COLUMN",
            "schema_name": schema_name,
            "table_name": column.table_name,
            "table_comment": table_comment,
            "column_name": column.name,
            "comment": column.comment,
            "data_type": column.data_type,
            "nullable": column.nullable,
            "is_primary_key": column.is_primary_key,
            "is_unique": column.is_unique,
            "ordinal": column.ordinal,
            "relations": [
                {
                    "name": r.name,
                    "referenced_schema_name": r.referenced_schema_name,
                    "referenced_table_name": r.referenced_table_name,
                    "columns": [
                        {
                            "column": m.column,
                            "referenced_column": m.referenced_column,
                        }
                        for m in r.columns
                    ],
                }
                for r in relations
            ],
        }
    )


__all__ = [
    "RebuildResult",
    "build_documents_for_revision",
    "rebuild_for_active_source",
    "rebuild_for_revision",
]
