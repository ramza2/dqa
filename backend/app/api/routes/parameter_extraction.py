"""Parameter Extraction API (advisory extraction + deterministic validation)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.adapters.parameter_extraction.errors import (
    ParameterExtractionError,
    ParameterExtractionErrorCode,
)
from app.api.public_errors import PublicErrorSpec, build_public_http_error
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.parameter_extraction import (
    ParameterExtractionRequest,
    ParameterExtractionResponse,
)
from app.services.parameter_extraction import extract_query_parameters

router = APIRouter(prefix="/api/v1", tags=["query-parameters"])

_EXTRACTION_PUBLIC_ERRORS = {
    ParameterExtractionErrorCode.TEMPLATE_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "query template not found",
    ),
    ParameterExtractionErrorCode.ACTIVE_CATALOG_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "active catalog revision not found for source",
    ),
    ParameterExtractionErrorCode.TEMPLATE_NOT_ELIGIBLE: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "query template is not eligible for parameter extraction",
    ),
    ParameterExtractionErrorCode.STALE_VERSION: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "requested version is not the current template version",
    ),
    ParameterExtractionErrorCode.EGRESS_NOT_ALLOWED: PublicErrorSpec(
        status.HTTP_403_FORBIDDEN,
        "parameter extraction raw-request egress is not approved",
    ),
    ParameterExtractionErrorCode.PROMPT_TOO_LARGE: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "parameter extraction prompt exceeds the configured size limit",
    ),
    ParameterExtractionErrorCode.PARAMETER_SCHEMA_INVALID: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "template parameter schema is invalid",
    ),
    ParameterExtractionErrorCode.LLM_NOT_CONFIGURED: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "LLM provider is not configured",
    ),
    ParameterExtractionErrorCode.LLM_UNAVAILABLE: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "LLM provider is temporarily unavailable",
    ),
    ParameterExtractionErrorCode.LLM_OUTPUT_INVALID: PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "LLM provider returned an invalid extraction response",
    ),
}


@router.post(
    "/query-parameters/extract",
    response_model=ParameterExtractionResponse,
)
def extract_parameters(
    body: ParameterExtractionRequest,
    response: Response,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.QUERY_OPERATE)
    ),
) -> ParameterExtractionResponse:
    """Extract declared parameter values for one eligible Query Template version.

    Does not execute SQL. Raw request egress requires an explicit settings gate.
    """
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    try:
        return extract_query_parameters(session, body)
    except ParameterExtractionError as exc:
        raise _extraction_http_error(exc) from None


def _extraction_http_error(exc: ParameterExtractionError) -> HTTPException:
    return build_public_http_error(
        error_code=exc.code,
        contracts=_EXTRACTION_PUBLIC_ERRORS,
        fallback_code=ParameterExtractionErrorCode.INTERNAL_ERROR,
        fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        fallback_message="parameter extraction failed",
    )
