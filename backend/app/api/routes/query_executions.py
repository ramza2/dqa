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
from app.api.public_errors import PublicErrorSpec, build_public_http_error
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

_ELIGIBILITY_PUBLIC_ERRORS = {
    ExecutionPreviewErrorCode.TEMPLATE_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "query template not found",
    ),
    ExecutionPreviewErrorCode.ACTIVE_CATALOG_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "active catalog revision not found",
    ),
    ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "connection profile not found",
    ),
    ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "query template is not eligible for execution",
    ),
    ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "requested template version is stale",
    ),
    ExecutionPreviewErrorCode.CATALOG_MISMATCH: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "query template is incompatible with the active catalog",
    ),
    ExecutionPreviewErrorCode.CONNECTION_PROFILE_DISABLED: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "connection profile is disabled",
    ),
    ExecutionPreviewErrorCode.CONNECTION_PROFILE_INCOMPLETE: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "connection profile is incomplete",
    ),
    ExecutionPreviewErrorCode.SQL_UNSAFE: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "query template SQL does not pass safety validation",
    ),
    ExecutionPreviewErrorCode.PARAMETER_SCHEMA_INVALID: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "query template parameter schema is invalid",
    ),
    ExecutionPreviewErrorCode.PARAMETER_UNDECLARED: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "request contains an undeclared parameter",
    ),
    ExecutionPreviewErrorCode.PARAMETER_INVALID: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "query parameter values are invalid",
    ),
}

_EXECUTION_PUBLIC_ERRORS = {
    ExecutionErrorCode.AUDIT_UNAVAILABLE: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "query audit is unavailable",
    ),
    ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS read-only adapter is unavailable",
    ),
}

_ADAPTER_PUBLIC_ERRORS = {
    DemisAdapterErrorCode.TIMEOUT: PublicErrorSpec(
        status.HTTP_504_GATEWAY_TIMEOUT,
        "DEMIS read-only query execution timed out",
    ),
    DemisAdapterErrorCode.UNSUPPORTED_DBMS: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS database type is not supported",
    ),
    DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS credential is unavailable",
    ),
    DemisAdapterErrorCode.CONNECTION_FAILED: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS read-only connection could not be established",
    ),
    DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS read-only adapter is not configured",
    ),
    DemisAdapterErrorCode.PROFILE_DISABLED: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "DEMIS connection profile is disabled",
    ),
    DemisAdapterErrorCode.EXECUTION_FAILED: PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "DEMIS read-only query execution failed",
    ),
    DemisAdapterErrorCode.RESULT_LIMIT_ERROR: PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "DEMIS query result limit could not be enforced",
    ),
    DemisAdapterErrorCode.INVALID_REQUEST: PublicErrorSpec(
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
    return build_public_http_error(
        error_code=exc.code,
        contracts=_ELIGIBILITY_PUBLIC_ERRORS,
        fallback_code=ExecutionPreviewErrorCode.INTERNAL_ERROR,
        fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        fallback_message="query execution eligibility check failed",
    )


def _execution_http_error(exc: ExecutionError) -> HTTPException:
    return build_public_http_error(
        error_code=exc.code,
        contracts=_EXECUTION_PUBLIC_ERRORS,
        fallback_code=ExecutionErrorCode.INTERNAL_ERROR,
        fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        fallback_message="query execution failed",
    )


def _adapter_http_error(exc: DemisAdapterError) -> HTTPException:
    return build_public_http_error(
        error_code=exc.code,
        contracts=_ADAPTER_PUBLIC_ERRORS,
        fallback_code=DemisAdapterErrorCode.EXECUTION_FAILED,
        fallback_status_code=status.HTTP_502_BAD_GATEWAY,
        fallback_message="DEMIS read-only operation failed",
    )
