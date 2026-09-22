"""Draft Query Template registry endpoints (no approval / execution)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.adapters.catalog.query_template_errors import (
    QueryTemplateError,
    QueryTemplateErrorCode,
)
from app.adapters.db.deps import get_db_session
from app.schemas.query_template import (
    QueryTemplateCreateRequest,
    QueryTemplateDetail,
    QueryTemplateListResponse,
    QueryTemplateUpdateRequest,
)
from app.services.query_template import (
    create_query_template,
    delete_query_template,
    get_query_template,
    list_query_templates,
    update_query_template,
)

router = APIRouter(prefix="/api/v1/query-templates", tags=["query-templates"])


@router.post("", response_model=QueryTemplateDetail, status_code=status.HTTP_201_CREATED)
def create_template(
    body: QueryTemplateCreateRequest,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    try:
        return create_query_template(session, body)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc
    except CatalogQueryError as exc:
        raise _catalog_query_http_error(exc) from exc


@router.get("", response_model=QueryTemplateListResponse)
def list_templates(
    source_name: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
) -> QueryTemplateListResponse:
    return list_query_templates(
        session,
        source_name=source_name,
        limit=limit,
        offset=offset,
    )


@router.get("/{template_id}", response_model=QueryTemplateDetail)
def get_template(
    template_id: int,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    try:
        return get_query_template(session, template_id)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.patch("/{template_id}", response_model=QueryTemplateDetail)
def patch_template(
    template_id: int,
    body: QueryTemplateUpdateRequest,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    try:
        return update_query_template(session, template_id, body)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc
    except CatalogQueryError as exc:
        raise _catalog_query_http_error(exc) from exc


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_template(
    template_id: int,
    session: Session = Depends(get_db_session),
) -> Response:
    try:
        delete_query_template(session, template_id)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _template_http_error(exc: QueryTemplateError) -> HTTPException:
    if exc.code == QueryTemplateErrorCode.TEMPLATE_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == QueryTemplateErrorCode.DUPLICATE_STABLE_KEY:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code == QueryTemplateErrorCode.NOT_DRAFT:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code in {
        QueryTemplateErrorCode.INVALID_PARAMETER_SCHEMA,
        QueryTemplateErrorCode.INVALID_TARGET_SCHEMA,
        QueryTemplateErrorCode.INVALID_REQUEST,
    }:
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )


def _catalog_query_http_error(exc: CatalogQueryError) -> HTTPException:
    if exc.code == CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
        code = QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND
    else:
        status_code = status.HTTP_400_BAD_REQUEST
        code = exc.code
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": exc.issue.message},
    )
