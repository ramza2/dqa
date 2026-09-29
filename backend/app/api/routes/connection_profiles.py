"""Connection Profile management endpoints (no live DEMIS connectivity)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.connection_profile.errors import (
    ConnectionProfileError,
    ConnectionProfileErrorCode,
)
from app.adapters.db.deps import get_db_session
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.connection_profile import (
    ConnectionProfileCreateRequest,
    ConnectionProfileDiagnosticsResponse,
    ConnectionProfileListResponse,
    ConnectionProfileUpdateRequest,
    ConnectionProfileView,
)
from app.services.connection_profile import (
    create_connection_profile,
    disable_connection_profile,
    enable_connection_profile,
    get_connection_profile,
    get_connection_profile_diagnostics,
    list_connection_profiles,
    update_connection_profile,
)

router = APIRouter(prefix="/api/v1/connection-profiles", tags=["connection-profiles"])


@router.post("", response_model=ConnectionProfileView, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ConnectionProfileCreateRequest,
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> ConnectionProfileView:
    try:
        return create_connection_profile(session, body, actor=actor.actor_id)
    except ConnectionProfileError as exc:
        raise _profile_http_error(exc) from None


@router.get("", response_model=ConnectionProfileListResponse)
def list_profiles(
    source_name: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> ConnectionProfileListResponse:
    return list_connection_profiles(
        session,
        source_name=source_name,
        environment=environment,
        limit=limit,
        offset=offset,
    )


@router.get("/{profile_id}", response_model=ConnectionProfileView)
def get_profile(
    profile_id: int,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> ConnectionProfileView:
    try:
        return get_connection_profile(session, profile_id)
    except ConnectionProfileError as exc:
        raise _profile_http_error(exc) from None


@router.patch("/{profile_id}", response_model=ConnectionProfileView)
def patch_profile(
    profile_id: int,
    body: ConnectionProfileUpdateRequest,
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> ConnectionProfileView:
    try:
        return update_connection_profile(
            session, profile_id, body, actor=actor.actor_id
        )
    except ConnectionProfileError as exc:
        raise _profile_http_error(exc) from None


@router.post("/{profile_id}/enable", response_model=ConnectionProfileView)
def enable_profile(
    profile_id: int,
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> ConnectionProfileView:
    try:
        return enable_connection_profile(session, profile_id, actor=actor.actor_id)
    except ConnectionProfileError as exc:
        raise _profile_http_error(exc) from None


@router.post("/{profile_id}/disable", response_model=ConnectionProfileView)
def disable_profile(
    profile_id: int,
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> ConnectionProfileView:
    try:
        return disable_connection_profile(session, profile_id, actor=actor.actor_id)
    except ConnectionProfileError as exc:
        raise _profile_http_error(exc) from None


@router.get(
    "/{profile_id}/diagnostics",
    response_model=ConnectionProfileDiagnosticsResponse,
)
def profile_diagnostics(
    profile_id: int,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> ConnectionProfileDiagnosticsResponse:
    try:
        return get_connection_profile_diagnostics(session, profile_id)
    except ConnectionProfileError as exc:
        raise _profile_http_error(exc) from None


def _profile_http_error(exc: ConnectionProfileError) -> HTTPException:
    if exc.code == ConnectionProfileErrorCode.NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == ConnectionProfileErrorCode.DUPLICATE_SOURCE_ENVIRONMENT:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code == ConnectionProfileErrorCode.INVALID_REQUEST:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )
