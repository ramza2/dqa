"""Parameter Extraction API (advisory extraction + deterministic validation)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.adapters.parameter_extraction.errors import (
    ParameterExtractionError,
    ParameterExtractionErrorCode,
)
from app.schemas.parameter_extraction import (
    ParameterExtractionRequest,
    ParameterExtractionResponse,
)
from app.services.parameter_extraction import extract_query_parameters

router = APIRouter(prefix="/api/v1", tags=["query-parameters"])


@router.post(
    "/query-parameters/extract",
    response_model=ParameterExtractionResponse,
)
def extract_parameters(
    body: ParameterExtractionRequest,
    response: Response,
    session: Session = Depends(get_db_session),
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
    if exc.code == ParameterExtractionErrorCode.TEMPLATE_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == ParameterExtractionErrorCode.ACTIVE_CATALOG_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code in {
        ParameterExtractionErrorCode.TEMPLATE_NOT_ELIGIBLE,
        ParameterExtractionErrorCode.STALE_VERSION,
    }:
        status_code = status.HTTP_409_CONFLICT
    elif exc.code == ParameterExtractionErrorCode.EGRESS_NOT_ALLOWED:
        status_code = status.HTTP_403_FORBIDDEN
    elif exc.code in {
        ParameterExtractionErrorCode.PROMPT_TOO_LARGE,
        ParameterExtractionErrorCode.PARAMETER_SCHEMA_INVALID,
    }:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    elif exc.code in {
        ParameterExtractionErrorCode.LLM_NOT_CONFIGURED,
        ParameterExtractionErrorCode.LLM_UNAVAILABLE,
    }:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code == ParameterExtractionErrorCode.LLM_OUTPUT_INVALID:
        status_code = status.HTTP_502_BAD_GATEWAY
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )
