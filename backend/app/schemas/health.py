"""Health check response schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Liveness response: the API process is up."""

    status: Literal["ok"] = "ok"
    service: str = Field(description="Application service name")
    environment: str = Field(description="Configured APP_ENV value")


class ReadyResponse(BaseModel):
    """Readiness response: DQA PostgreSQL is reachable."""

    status: Literal["ready"] = "ready"
    database: Literal["ok"] = "ok"


class NotReadyResponse(BaseModel):
    """Readiness failure payload."""

    status: Literal["not_ready"] = "not_ready"
    database: Literal["unavailable"] = "unavailable"
    detail: str = Field(description="Sanitized failure reason")
