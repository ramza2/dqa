"""M5-S1A administrator-only external service policy drafts.

DRAFT/REVOKED rows carry no usable credential and grant zero REST/MCP access.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.service_client_draft import (
    ServiceClientDraftCreate, ServiceClientDraftEventView,
    ServiceClientDraftList, ServiceClientDraftPatch, ServiceClientDraftView,
)
from app.services.service_client_draft import (
    ServiceClientDraftError, create_client_draft, get_client_draft,
    list_client_draft_events, list_client_drafts, patch_client_draft,
    revoke_client_draft,
)

router = APIRouter(prefix="/api/v1/admin/service-clients", tags=["admin-service-clients"])


def _error(exc: ServiceClientDraftError) -> HTTPException:
    code = exc.code
    status_code = (
        status.HTTP_404_NOT_FOUND if code == "SERVICE_CLIENT_NOT_FOUND"
        else status.HTTP_409_CONFLICT
    )
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": "service client policy draft request rejected"},
    )


def _validated(model, raw: Any):
    try:
        return model.model_validate(raw)
    except ValidationError:
        # FastAPI's default 422 can echo rejected inputs (including misplaced secrets).
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "INVALID_SERVICE_CLIENT_DRAFT", "message": "invalid policy draft"},
        ) from None


@router.get("", response_model=ServiceClientDraftList)
def list_drafts(
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CONNECTION_PROFILE_MANAGE)),
) -> ServiceClientDraftList:
    total, items = list_client_drafts(session, limit=limit, offset=offset)
    return ServiceClientDraftList(total=total, items=[ServiceClientDraftView.model_validate(item) for item in items])


@router.post("", response_model=ServiceClientDraftView, status_code=status.HTTP_201_CREATED)
def create_draft(
    raw: Any = Body(...),
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(require_permission(Permission.CONNECTION_PROFILE_MANAGE)),
) -> ServiceClientDraftView:
    body = _validated(ServiceClientDraftCreate, raw)
    try:
        draft = create_client_draft(session, body, actor_id=actor.actor_id)
    except ServiceClientDraftError as exc:
        raise _error(exc) from None
    return ServiceClientDraftView.model_validate(draft)


@router.get("/{draft_id}", response_model=ServiceClientDraftView)
def get_draft(
    draft_id: int,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CONNECTION_PROFILE_MANAGE)),
) -> ServiceClientDraftView:
    try:
        return ServiceClientDraftView.model_validate(get_client_draft(session, draft_id))
    except ServiceClientDraftError as exc:
        raise _error(exc) from None


@router.patch("/{draft_id}", response_model=ServiceClientDraftView)
def patch_draft(
    draft_id: int,
    raw: Any = Body(...),
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(require_permission(Permission.CONNECTION_PROFILE_MANAGE)),
) -> ServiceClientDraftView:
    body = _validated(ServiceClientDraftPatch, raw)
    try:
        return ServiceClientDraftView.model_validate(
            patch_client_draft(session, draft_id, body, actor_id=actor.actor_id)
        )
    except ServiceClientDraftError as exc:
        raise _error(exc) from None


@router.post("/{draft_id}/revoke", response_model=ServiceClientDraftView)
def revoke_draft(
    draft_id: int,
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(require_permission(Permission.CONNECTION_PROFILE_MANAGE)),
) -> ServiceClientDraftView:
    try:
        return ServiceClientDraftView.model_validate(
            revoke_client_draft(session, draft_id, actor_id=actor.actor_id)
        )
    except ServiceClientDraftError as exc:
        raise _error(exc) from None


@router.get("/{draft_id}/events", response_model=list[ServiceClientDraftEventView])
def get_events(
    draft_id: int,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CONNECTION_PROFILE_MANAGE)),
) -> list[ServiceClientDraftEventView]:
    try:
        events = list_client_draft_events(session, draft_id)
    except ServiceClientDraftError as exc:
        raise _error(exc) from None
    return [ServiceClientDraftEventView.model_validate(event) for event in events]
