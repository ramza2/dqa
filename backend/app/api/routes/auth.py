"""Optional authenticated identity diagnostic endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.auth.dependencies import get_current_actor
from app.auth.models import AuthenticatedActor

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthMeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    roles: list[str] = Field(default_factory=list)
    provider: str


@router.get("/me", response_model=AuthMeResponse)
def auth_me(
    actor: AuthenticatedActor = Depends(get_current_actor),
) -> AuthMeResponse:
    """Return the authenticated actor (no login; identity assertion only)."""
    return AuthMeResponse(
        actor_id=actor.actor_id,
        roles=sorted(role.value for role in actor.roles),
        provider=actor.provider,
    )
