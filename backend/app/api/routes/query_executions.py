"""Query execution preview + execute + form metadata APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
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
from app.schemas.execution_form import ExecutionFormResponse
from app.schemas.execution_preview import (
    ExecutionPreviewRequest,
    ExecutionPreviewResponse,
)
from app.schemas.query_execution import QueryExecutionRequest, QueryExecutionResponse
from app.services.execution_form import get_execution_form_metadata
from app.services.execution_preview import preview_query_execution
from app.services.query_execution import execute_query

router = APIRouter(prefix="/api/v1/query-executions", tags=["query-executions"])

_ADAPTER_PUBLIC_ERRORS: dict[str, tuple[int, str]] = {
    DemisAdapterErrorCode.TIMEOUT: (
        status.HTTP_504_GATEWAY_TIMEOUT,
        "DEMIS read-only query execution timed out",
    ),
    DemisAdapterErrorCode.UNSUPPORTED_DBMS: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS database type is not supported",
    ),
    DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS credential is unavailable",
    ),
    DemisAdapterErrorCode.CONNECTION_FAILED: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS read-only connection could not be established",
    ),
    DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS read-only adapter is not configured",
    ),
    DemisAdapterErrorCode.PROFILE_DISABLED: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS connection profile is disabled",
    ),
    DemisAdapterErrorCode.EXECUTION_FAILED: (
        status.HTTP_502_BAD_GATEWAY,
        "DEMIS read-only query execution failed",
    ),
    DemisAdapterErrorCode.RESULT_LIMIT_ERROR: (
        status.HTTP_502_BAD_GATEWAY,
        "DEMIS query result limit could not be enforced",
    ),
    DemisAdapterErrorCode.INVALID_REQUEST: (
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "DEMIS read-only query request is invalid",
    ),
}


@router.get("/form", response_model=ExecutionFormResponse)
def execution_form_metadata(
    response: Response,
    source_name: str = Query(min_length=1, max_length=255),
    template_id: int = Query(gt=0),
    version_id: int = Query(gt=0),
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.QUERY_OPERATE)
    ),
) -> ExecutionFormResponse:
    """QUERY_OPERATE-safe parameter + environment metadata for Query Assistant."""
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    try:
        return get_execution_form_metadata(
            session,
            source_name=source_name,
            template_id=template_id,
            version_id=version_id,
        )
    except ExecutionPreviewError as exc:
        raise _eligibility_http_error(exc) from None


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
    mapped = _ADAPTER_PUBLIC_ERRORS.get(exc.code)
    if mapped is None:
        public_code = DemisAdapterErrorCode.EXECUTION_FAILED
        status_code = status.HTTP_502_BAD_GATEWAY
        message = "DEMIS read-only operation failed"
    else:
        public_code = exc.code
        status_code, message = mapped
    return HTTPException(
        status_code=status_code,
        detail={"code": public_code, "message": message},
    )
