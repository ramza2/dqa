"""Query execution preview + execute APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.execution.errors import (
    ExecutionError,
    ExecutionErrorCode,
    ExecutionPreviewError,
    ExecutionPreviewErrorCode,
)
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.execution_preview import (
    ExecutionPreviewRequest,
    ExecutionPreviewResponse,
)
from app.schemas.query_execution import QueryExecutionRequest, QueryExecutionResponse
from app.services.execution_preview import preview_query_execution
from app.services.query_execution import execute_query

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
        raise _eligibility_http_error(exc) from None


@router.post("/execute", response_model=QueryExecutionResponse)
def execute_execution(
    body: QueryExecutionRequest,
    response: Response,
    session: Session = Depends(get_db_session),
    actor: AuthenticatedActor = Depends(
        require_permission(Permission.QUERY_OPERATE)
    ),
) -> QueryExecutionResponse:
    """Explicit read-only execution action with durable audit lifecycle."""
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    try:
        return execute_query(session, body, actor=actor)
    except ExecutionPreviewError as exc:
        raise _eligibility_http_error(exc) from None
    except ExecutionError as exc:
        raise _execution_http_error(exc) from None
    except DemisAdapterError as exc:
        raise _adapter_http_error(exc) from None


def _eligibility_http_error(exc: ExecutionPreviewError) -> HTTPException:
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


def _execution_http_error(exc: ExecutionError) -> HTTPException:
    if exc.code in {
        ExecutionErrorCode.AUDIT_UNAVAILABLE,
        ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE,
    }:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )


def _adapter_http_error(exc: DemisAdapterError) -> HTTPException:
    if exc.code == DemisAdapterErrorCode.TIMEOUT:
        status_code = status.HTTP_504_GATEWAY_TIMEOUT
    elif exc.code in {
        DemisAdapterErrorCode.UNSUPPORTED_DBMS,
        DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
        DemisAdapterErrorCode.CONNECTION_FAILED,
        DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED,
        DemisAdapterErrorCode.PROFILE_DISABLED,
    }:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code in {
        DemisAdapterErrorCode.EXECUTION_FAILED,
        DemisAdapterErrorCode.RESULT_LIMIT_ERROR,
    }:
        status_code = status.HTTP_502_BAD_GATEWAY
    elif exc.code == DemisAdapterErrorCode.INVALID_REQUEST:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_502_BAD_GATEWAY
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": str(exc)},
    )
