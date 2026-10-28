"""Metadata-allowlisted SQL *display* preview; not Phase 29-D or execution.

Catalog truth is sufficient only for a physical-schema preview. This does not
infer logical clinical fields, approve Semantic Resources, register templates,
resolve credentials, or create an executable authority.
"""
from __future__ import annotations

import re
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryError
from app.domain.query_compiler import ORACLE_IDENT_PATTERN
from app.schemas.catalog_preview import (
    CatalogPreviewParameter,
    CatalogPreviewRequest,
    CatalogPreviewResponse,
)
from app.schemas.query_template import QueryTemplateParameter
from app.services.catalog_query import _doc_list, _map_column, _map_table, resolve_active_revision
from app.services.sql_safety import validate_sql_safety

_IDENT = re.compile(ORACLE_IDENT_PATTERN)


class CatalogPreviewError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _ident(name: str) -> str:
    # Do not strip or escape caller strings into valid identifiers: this must
    # match a real active Catalog object AND Oracle's restricted identifier set.
    if not isinstance(name, str) or not _IDENT.fullmatch(name):
        raise CatalogPreviewError("INVALID_IDENTIFIER")
    return f'"{name}"'


def preview_catalog_query(session: Session, body: CatalogPreviewRequest) -> CatalogPreviewResponse:
    try:
        active = resolve_active_revision(session, body.source_name)
    except CatalogQueryError:
        raise CatalogPreviewError("ACTIVE_CATALOG_NOT_FOUND") from None

    if (
        active.source_name != body.source_name
        or active.revision_id != body.catalog_revision_id
        or active.schema_fingerprint != body.schema_fingerprint
    ):
        raise CatalogPreviewError("CATALOG_MISMATCH")

    # Scope to exactly one authoritative table. Ambiguous/duplicate snapshots
    # do not authorize generating new SQL even for a preview.
    tables = [
        _map_table(item, {})
        for item in _doc_list(active.revision.tables_json, "tables")
    ]
    table_matches = [
        item for item in tables
        if item.schema_name == body.schema_name and item.name == body.table_name
    ]
    if len(table_matches) != 1:
        raise CatalogPreviewError("TABLE_NOT_UNIQUE_OR_MISSING")
    schema_sql = _ident(table_matches[0].schema_name)
    table_sql = _ident(table_matches[0].name)

    all_columns = [
        _map_column(item) for item in _doc_list(active.revision.columns_json, "columns")
    ]
    column_index: dict[str, list] = {}
    for item in all_columns:
        if item.schema_name == body.schema_name and item.table_name == body.table_name:
            column_index.setdefault(item.name, []).append(item)

    def require_column(name: str):
        items = column_index.get(name, [])
        if len(items) != 1:
            raise CatalogPreviewError("COLUMN_NOT_UNIQUE_OR_MISSING")
        _ident(items[0].name)
        return items[0]

    select_sql = ", ".join(_ident(require_column(name).name) for name in body.columns)
    where_parts: list[str] = []
    params: list[CatalogPreviewParameter] = []
    param_schema: list[QueryTemplateParameter] = []

    for idx, predicate in enumerate(body.predicates, start=1):
        column = require_column(predicate.column)
        lhs = _ident(column.name)
        operator = predicate.operator
        if operator in {"IS_NULL", "IS_NOT_NULL"}:
            where_parts.append(f"{lhs} IS {'NOT ' if operator == 'IS_NOT_NULL' else ''}NULL")
            continue
        db_type = (column.data_type or "").upper()
        is_text = any(db_type.startswith(x) for x in ("VARCHAR", "NVARCHAR", "CHAR", "NCHAR", "CLOB"))
        is_number = any(db_type.startswith(x) for x in ("NUMBER", "NUMERIC", "DECIMAL", "INTEGER", "INT", "FLOAT"))
        is_time = any(db_type.startswith(x) for x in ("DATE", "TIMESTAMP"))
        if not (is_text or is_number or is_time):
            raise CatalogPreviewError("UNSUPPORTED_COLUMN_TYPE")
        if operator == "LIKE" and not is_text:
            raise CatalogPreviewError("UNSUPPORTED_OPERATOR")
        param_type = "string" if is_text else "decimal" if is_number else "datetime" if db_type.startswith("TIMESTAMP") else "date"
        name = f"p{idx}"
        sqlop = {"EQ": "=", "NE": "<>", "LT": "<", "LE": "<=", "GT": ">", "GE": ">=", "LIKE": "LIKE"}[operator]
        where_parts.append(f"{lhs} {sqlop} :{name}")
        params.append(CatalogPreviewParameter(name=name, column=column.name, type=param_type))
        param_schema.append(QueryTemplateParameter(name=name, type=param_type))

    base = f"SELECT {select_sql} FROM {schema_sql}.{table_sql}"
    if where_parts:
        base += " WHERE " + " AND ".join(where_parts)
    # Template-style bound limit. Returned placeholders are intentionally
    # unresolved: caller is NOT handed an executable plan or DB adapter.
    outer_select = ", ".join(
        f'q.{_ident(require_column(name).name)}' for name in body.columns
    )
    sql_text = f"SELECT {outer_select} FROM ({base}) q WHERE ROWNUM <= :p_limit"
    param_schema.append(QueryTemplateParameter(name="p_limit", type="integer"))
    params.append(CatalogPreviewParameter(name="p_limit", type="integer"))
    if not validate_sql_safety(sql_text, param_schema).safe:
        raise CatalogPreviewError("SQL_SAFETY_FAILED")

    return CatalogPreviewResponse(
        source_name=active.source_name,
        catalog_revision_id=active.revision_id,
        schema_fingerprint=active.schema_fingerprint,
        sql_text=sql_text,
        parameters=params,
    )
