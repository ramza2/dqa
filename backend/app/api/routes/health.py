"""Health and readiness endpoints."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.db.session import check_database_connectivity
from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse, NotReadyResponse, ReadyResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Liveness probe: process and API are responsive."""
    return HealthResponse(service=settings.app_name, environment=settings.app_env)


@router.get(
    "/health/ready",
    response_model=ReadyResponse | NotReadyResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": NotReadyResponse},
    },
)
def ready(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> ReadyResponse | NotReadyResponse:
    """Readiness probe: DQA PostgreSQL is reachable."""
    try:
        check_database_connectivity(settings)
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return NotReadyResponse(detail=_sanitize_db_error(settings))
    except OSError as exc:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return NotReadyResponse(detail=f"database unreachable: {exc.__class__.__name__}")
    return ReadyResponse()


def _sanitize_db_error(settings: Settings) -> str:
    """Return a failure message that does not leak credentials."""
    # Avoid echoing exception text that may contain host/user/password fragments.
    _ = settings.database_url_safe
    return "database check failed (SQLAlchemyError)"
