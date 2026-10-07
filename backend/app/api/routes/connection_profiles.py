"""Connection Profile management endpoints.

GET diagnostics remain configuration-only. Live DEMIS connectivity is available
only through explicit POST ``/test-connection`` (administrator).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.adapters.connection_profile.errors import (
    ConnectionProfileError,
    ConnectionProfileErrorCode,
)
from app.adapters.db.deps import get_db_session
from app.api.public_errors import PublicErrorSpec, build_public_http_error
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.connection_profile import (
    ConnectionProfileCreateRequest,
    ConnectionProfileDiagnosticsResponse,
    ConnectionProfileListResponse,
    ConnectionProfileTestConnectionResponse,
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
    test_connection_profile_live_connection,
    update_connection_profile,
)

router = APIRouter(prefix="/api/v1/connection-profiles", tags=["connection-profiles"])

_PROFILE_PUBLIC_ERRORS = {
    ConnectionProfileErrorCode.NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "connection profile not found",
    ),
    ConnectionProfileErrorCode.DUPLICATE_SOURCE_ENVIRONMENT: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "connection profile already exists for source and environment",
    ),
    ConnectionProfileErrorCode.INVALID_REQUEST: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "connection profile request is invalid",
    ),
}


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


@router.post(
    "/{profile_id}/test-connection",
    response_model=ConnectionProfileTestConnectionResponse,
)
def test_profile_connection(
    profile_id: int,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
) -> ConnectionProfileTestConnectionResponse:
    try:
        return test_connection_profile_live_connection(session, profile_id)
    except ConnectionProfileError as exc:
        raise _profile_http_error(exc) from None


def _profile_http_error(exc: ConnectionProfileError) -> HTTPException:
    return build_public_http_error(
        error_code=exc.code,
        contracts=_PROFILE_PUBLIC_ERRORS,
        fallback_code=ConnectionProfileErrorCode.INTERNAL_ERROR,
        fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        fallback_message="connection profile operation failed",
    )
