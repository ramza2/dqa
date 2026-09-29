"""Query execution preview API (eligibility only; no live DEMIS execution)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.adapters.execution.errors import (
    ExecutionPreviewError,
    ExecutionPreviewErrorCode,
)
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.execution_preview import (
    ExecutionPreviewRequest,
    ExecutionPreviewResponse,
)
from app.services.execution_preview import preview_query_execution

router = APIRouter(prefix="/api/v1/query-executions", tags=["query-executions"])


@router.post("/preview", response_model=ExecutionPreviewResponse)
def preview_execution(
    body: ExecutionPreviewRequest,
    response: Response,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.QUERY_OPERATE)
    ),
) -> ExecutionPreviewResponse:
    """Preview deterministic execution eligibility without contacting DEMIS."""
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    try:
        return preview_query_execution(session, body)
    except ExecutionPreviewError as exc:
        raise _preview_http_error(exc) from None


def _preview_http_error(exc: ExecutionPreviewError) -> HTTPException:
    if exc.code in {
        ExecutionPreviewErrorCode.TEMPLATE_NOT_FOUND,
        ExecutionPreviewErrorCode.ACTIVE_CATALOG_NOT_FOUND,
        ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND,
    }:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE,
        ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION,
        ExecutionPreviewErrorCode.CATALOG_MISMATCH,
        ExecutionPreviewErrorCode.CONNECTION_PROFILE_DISABLED,
        ExecutionPreviewErrorCode.CONNECTION_PROFILE_INCOMPLETE,
    }:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code in {
        ExecutionPreviewErrorCode.SQL_UNSAFE,
        ExecutionPreviewErrorCode.PARAMETER_SCHEMA_INVALID,
        ExecutionPreviewErrorCode.PARAMETER_UNDECLARED,
        ExecutionPreviewErrorCode.PARAMETER_INVALID,
    }:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )
