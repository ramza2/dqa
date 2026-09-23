"""Query Template registry and approval workflow endpoints (no execution)."""

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
    QueryTemplateNewVersionRequest,
    QueryTemplateNoteRequest,
    QueryTemplateRejectRequest,
    QueryTemplateReviewEventListResponse,
    QueryTemplateUpdateRequest,
    QueryTemplateVersionListResponse,
)
from app.schemas.sql_safety import QueryTemplateSqlSafetyResponse
from app.services.query_template import (
    approve_query_template,
    create_query_template,
    create_query_template_version,
    delete_query_template,
    disable_query_template,
    enable_query_template,
    get_query_template,
    get_query_template_sql_safety,
    list_query_template_review_events,
    list_query_template_versions,
    list_query_templates,
    reject_query_template,
    submit_query_template_for_review,
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


@router.post("/{template_id}/submit-review", response_model=QueryTemplateDetail)
def submit_review(
    template_id: int,
    body: QueryTemplateNoteRequest | None = None,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    note = body.note if body is not None else None
    try:
        return submit_query_template_for_review(
            session, template_id, note=note, actor=None
        )
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.post("/{template_id}/approve", response_model=QueryTemplateDetail)
def approve(
    template_id: int,
    body: QueryTemplateNoteRequest | None = None,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    note = body.note if body is not None else None
    try:
        return approve_query_template(session, template_id, note=note, actor=None)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.post("/{template_id}/reject", response_model=QueryTemplateDetail)
def reject(
    template_id: int,
    body: QueryTemplateRejectRequest,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    try:
        return reject_query_template(
            session, template_id, note=body.note, actor=None
        )
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.post(
    "/{template_id}/versions",
    response_model=QueryTemplateDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    template_id: int,
    body: QueryTemplateNewVersionRequest | None = None,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    try:
        return create_query_template_version(
            session, template_id, body, actor=None
        )
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.get("/{template_id}/versions", response_model=QueryTemplateVersionListResponse)
def list_versions(
    template_id: int,
    session: Session = Depends(get_db_session),
) -> QueryTemplateVersionListResponse:
    try:
        return list_query_template_versions(session, template_id)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.get(
    "/{template_id}/review-events",
    response_model=QueryTemplateReviewEventListResponse,
)
def list_review_events(
    template_id: int,
    session: Session = Depends(get_db_session),
) -> QueryTemplateReviewEventListResponse:
    try:
        return list_query_template_review_events(session, template_id)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.get("/{template_id}/sql-safety", response_model=QueryTemplateSqlSafetyResponse)
def get_sql_safety(
    template_id: int,
    session: Session = Depends(get_db_session),
) -> QueryTemplateSqlSafetyResponse:
    try:
        return get_query_template_sql_safety(session, template_id)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.post("/{template_id}/enable", response_model=QueryTemplateDetail)
def enable(
    template_id: int,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    try:
        return enable_query_template(session, template_id)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


@router.post("/{template_id}/disable", response_model=QueryTemplateDetail)
def disable(
    template_id: int,
    session: Session = Depends(get_db_session),
) -> QueryTemplateDetail:
    try:
        return disable_query_template(session, template_id)
    except QueryTemplateError as exc:
        raise _template_http_error(exc) from exc


def _template_http_error(exc: QueryTemplateError) -> HTTPException:
    if exc.code in {
        QueryTemplateErrorCode.TEMPLATE_NOT_FOUND,
        QueryTemplateErrorCode.VERSION_NOT_FOUND,
        QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND,
    }:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        QueryTemplateErrorCode.DUPLICATE_STABLE_KEY,
        QueryTemplateErrorCode.NOT_DRAFT,
        QueryTemplateErrorCode.INVALID_TRANSITION,
        QueryTemplateErrorCode.STABLE_METADATA_FROZEN,
        QueryTemplateErrorCode.INCOMPATIBLE_CATALOG,
    }:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code in {
        QueryTemplateErrorCode.INVALID_PARAMETER_SCHEMA,
        QueryTemplateErrorCode.INVALID_TARGET_SCHEMA,
        QueryTemplateErrorCode.INVALID_REQUEST,
    }:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
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
