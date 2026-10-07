"""Query Template recommendation endpoint (advisory ranking only; no execution)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.adapters.recommendation.errors import RecommendationError, RecommendationErrorCode
from app.api.public_errors import PublicErrorSpec, build_public_http_error
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.recommendation import (
    TemplateRecommendationRequest,
    TemplateRecommendationResponse,
)
from app.services.template_recommendation import recommend_query_templates

router = APIRouter(prefix="/api/v1", tags=["query-recommendations"])

_RECOMMENDATION_PUBLIC_ERRORS = {
    RecommendationErrorCode.ACTIVE_CATALOG_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "active catalog revision not found for source",
    ),
    RecommendationErrorCode.LLM_NOT_CONFIGURED: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "LLM provider is not configured",
    ),
    RecommendationErrorCode.LLM_UNAVAILABLE: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "LLM provider is temporarily unavailable",
    ),
    RecommendationErrorCode.EGRESS_NOT_ALLOWED: PublicErrorSpec(
        status.HTTP_403_FORBIDDEN,
        "template recommendation LLM egress is not allowed",
    ),
    RecommendationErrorCode.LLM_OUTPUT_INVALID: PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "LLM provider returned an invalid ranking response",
    ),
    RecommendationErrorCode.INVALID_REQUEST: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "recommendation request is invalid",
    ),
    RecommendationErrorCode.PROMPT_TOO_LARGE: PublicErrorSpec(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "recommendation prompt exceeds the configured size limit",
    ),
}


@router.post(
    "/query-recommendations",
    response_model=TemplateRecommendationResponse,
)
def create_query_recommendation(
    body: TemplateRecommendationRequest,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.QUERY_OPERATE)
    ),
) -> TemplateRecommendationResponse:
    """Recommend an eligible Query Template from a natural-language request.

    Raw request text is not sent to the LLM. Recommendation is not execution
    permission and does not extract parameters or run SQL.
    """
    try:
        return recommend_query_templates(session, body)
    except RecommendationError as exc:
        raise _recommendation_http_error(exc) from None


def _recommendation_http_error(exc: RecommendationError) -> HTTPException:
    return build_public_http_error(
        error_code=exc.code,
        contracts=_RECOMMENDATION_PUBLIC_ERRORS,
        fallback_code=RecommendationErrorCode.INTERNAL_ERROR,
        fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        fallback_message="template recommendation failed",
    )
