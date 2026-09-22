"""Active Catalog metadata query endpoints (tables/columns/relations/indexes/categories)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.adapters.db.deps import get_db_session
from app.schemas.catalog_query import (
    CatalogCategoryListResponse,
    CatalogColumnListResponse,
    CatalogIndexListResponse,
    CatalogRelationListResponse,
    CatalogTableDetailResponse,
    CatalogTableListResponse,
)
from app.services.catalog_query import (
    PageResult,
    ResolvedActiveRevision,
    get_table,
    list_categories,
    list_columns,
    list_indexes,
    list_relations,
    list_tables,
)

query_router = APIRouter(prefix="/api/v1/catalog/active", tags=["catalog-query"])


def _envelope(
    resolved: ResolvedActiveRevision,
    page: PageResult,
) -> dict[str, Any]:
    return {
        "source_name": resolved.source_name,
        "revision_id": resolved.revision_id,
        "schema_fingerprint": resolved.schema_fingerprint,
        "total": page.total,
        "limit": page.limit,
        "offset": page.offset,
        "items": page.items,
    }


def _query_http_error(exc: CatalogQueryError) -> HTTPException:
    if exc.code in {
        CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND,
        CatalogQueryErrorCode.TABLE_NOT_FOUND,
    }:
        status_code = status.HTTP_404_NOT_FOUND
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )


@query_router.get("/{source_name}/tables", response_model=CatalogTableListResponse)
def get_tables(
    source_name: str,
    q: str | None = Query(default=None),
    schema_name: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> CatalogTableListResponse:
    """List tables from the current active Catalog revision."""
    try:
        resolved, page = list_tables(
            session,
            source_name,
            q=q,
            schema_name=schema_name,
            category=category,
            limit=limit,
            offset=offset,
        )
    except CatalogQueryError as exc:
        raise _query_http_error(exc) from exc
    return CatalogTableListResponse(**_envelope(resolved, page))


@query_router.get(
    "/{source_name}/tables/{schema_name}/{table_name}",
    response_model=CatalogTableDetailResponse,
)
def get_table_detail(
    source_name: str,
    schema_name: str,
    table_name: str,
    session: Session = Depends(get_db_session),
) -> CatalogTableDetailResponse:
    """Return one schema-qualified table from the active Catalog revision."""
    try:
        resolved, item = get_table(session, source_name, schema_name, table_name)
    except CatalogQueryError as exc:
        raise _query_http_error(exc) from exc
    return CatalogTableDetailResponse(
        source_name=resolved.source_name,
        revision_id=resolved.revision_id,
        schema_fingerprint=resolved.schema_fingerprint,
        item=item,
    )


@query_router.get("/{source_name}/columns", response_model=CatalogColumnListResponse)
def get_columns(
    source_name: str,
    q: str | None = Query(default=None),
    schema_name: str | None = Query(default=None),
    table_name: str | None = Query(default=None),
    is_primary_key: bool | None = Query(default=None),
    is_unique: bool | None = Query(default=None),
    nullable: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> CatalogColumnListResponse:
    """List columns from the current active Catalog revision."""
    try:
        resolved, page = list_columns(
            session,
            source_name,
            q=q,
            schema_name=schema_name,
            table_name=table_name,
            is_primary_key=is_primary_key,
            is_unique=is_unique,
            nullable=nullable,
            limit=limit,
            offset=offset,
        )
    except CatalogQueryError as exc:
        raise _query_http_error(exc) from exc
    return CatalogColumnListResponse(**_envelope(resolved, page))


@query_router.get("/{source_name}/relations", response_model=CatalogRelationListResponse)
def get_relations(
    source_name: str,
    schema_name: str | None = Query(default=None),
    table_name: str | None = Query(default=None),
    referenced_table_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> CatalogRelationListResponse:
    """List FK relations from the current active Catalog revision."""
    try:
        resolved, page = list_relations(
            session,
            source_name,
            schema_name=schema_name,
            table_name=table_name,
            referenced_table_name=referenced_table_name,
            limit=limit,
            offset=offset,
        )
    except CatalogQueryError as exc:
        raise _query_http_error(exc) from exc
    return CatalogRelationListResponse(**_envelope(resolved, page))


@query_router.get("/{source_name}/indexes", response_model=CatalogIndexListResponse)
def get_indexes(
    source_name: str,
    schema_name: str | None = Query(default=None),
    table_name: str | None = Query(default=None),
    unique: bool | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> CatalogIndexListResponse:
    """List indexes from the current active Catalog revision."""
    try:
        resolved, page = list_indexes(
            session,
            source_name,
            schema_name=schema_name,
            table_name=table_name,
            unique=unique,
            limit=limit,
            offset=offset,
        )
    except CatalogQueryError as exc:
        raise _query_http_error(exc) from exc
    return CatalogIndexListResponse(**_envelope(resolved, page))


@query_router.get("/{source_name}/categories", response_model=CatalogCategoryListResponse)
def get_categories(
    source_name: str,
    q: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> CatalogCategoryListResponse:
    """List categories and table assignments from the active Catalog revision."""
    try:
        resolved, page = list_categories(
            session,
            source_name,
            q=q,
            limit=limit,
            offset=offset,
        )
    except CatalogQueryError as exc:
        raise _query_http_error(exc) from exc
    return CatalogCategoryListResponse(**_envelope(resolved, page))
