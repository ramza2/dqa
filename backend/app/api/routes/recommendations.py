"""Query Template recommendation endpoint (advisory ranking only; no execution)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.adapters.recommendation.errors import RecommendationError, RecommendationErrorCode
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.recommendation import (
    TemplateRecommendationRequest,
    TemplateRecommendationResponse,
)
from app.services.template_recommendation import recommend_query_templates

router = APIRouter(prefix="/api/v1", tags=["query-recommendations"])


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
    if exc.code == RecommendationErrorCode.ACTIVE_CATALOG_NOT_FOUND:
        status_code = status.HTTP_404_NOT_FOUND
    elif exc.code == RecommendationErrorCode.LLM_NOT_CONFIGURED:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code == RecommendationErrorCode.LLM_UNAVAILABLE:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    elif exc.code == RecommendationErrorCode.EGRESS_NOT_ALLOWED:
        status_code = status.HTTP_403_FORBIDDEN
    elif exc.code == RecommendationErrorCode.LLM_OUTPUT_INVALID:
        status_code = status.HTTP_502_BAD_GATEWAY
    elif exc.code in {
        RecommendationErrorCode.INVALID_REQUEST,
        RecommendationErrorCode.PROMPT_TOO_LARGE,
    }:
        status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    return HTTPException(
        status_code=status_code,
        detail={"code": exc.code, "message": exc.issue.message},
    )
