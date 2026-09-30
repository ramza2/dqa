"""Query Audit Event read API (no public write/update/delete)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.adapters.audit.errors import AuditError, AuditErrorCode
from app.adapters.db.deps import get_db_session
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.audit import QueryAuditEventListResponse, QueryAuditEventView
from app.services.query_audit import (
    get_query_audit_events_by_audit_id,
    list_query_audit_events,
)

router = APIRouter(prefix="/api/v1/audit-events", tags=["audit-events"])


class QueryAuditEventBundleResponse(BaseModel):
    """All append-only rows sharing one audit_id."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str
    items: list[QueryAuditEventView] = Field(default_factory=list)


@router.get("", response_model=QueryAuditEventListResponse)
def list_audit_events(
    audit_id: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    source_name: str | None = Query(default=None),
    template_id: int | None = Query(default=None, gt=0),
    event_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.AUDIT_READ)),
) -> QueryAuditEventListResponse:
    try:
        return list_query_audit_events(
            session,
            audit_id=audit_id,
            actor_id=actor_id,
            source_name=source_name,
            template_id=template_id,
            event_type=event_type,
            status=status_filter,
            limit=limit,
            offset=offset,
        )
    except AuditError as exc:
        raise _audit_http_error(exc) from None


@router.get("/{audit_id}", response_model=QueryAuditEventBundleResponse)
def get_audit_events(
    audit_id: str,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.AUDIT_READ)),
) -> QueryAuditEventBundleResponse:
    try:
        items = get_query_audit_events_by_audit_id(session, audit_id)
    except AuditError as exc:
        raise _audit_http_error(exc) from None
    return QueryAuditEventBundleResponse(audit_id=audit_id.strip(), items=items)


def _audit_http_error(exc: AuditError) -> HTTPException:
    if exc.code == AuditErrorCode.NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == AuditErrorCode.INVALID_REQUEST:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )
