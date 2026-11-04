"""Authenticated identity and opt-in first-party operator login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.auth.dependencies import get_current_actor
from app.auth.dependencies import _auth_http_error
from app.auth.errors import AuthError, AuthErrorCode
from app.auth.local_session import (
    COOKIE_NAME, SESSION_TTL, csrf_for_token, login_with_password,
    revoke_session, validate_local_auth_settings, validate_origin,
)
from app.auth.models import AuthenticatedActor
from app.core.config import Settings, get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class AuthMeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    roles: list[str] = Field(default_factory=list)
    provider: str
    display_name: str | None = None
    csrf_token: str | None = None


class AuthCapabilities(BaseModel):
    login_supported: bool
    mode: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: SecretStr


class LoginResponse(BaseModel):
    authenticated: bool
    csrf_token: str


@router.get("/capabilities", response_model=AuthCapabilities)
def auth_capabilities(settings: Settings = Depends(get_settings)) -> AuthCapabilities:
    """Public, secret-free SPA bootstrap: never confers permissions."""
    if settings.dqa_auth_provider == "local_session":
        try:
            validate_local_auth_settings(settings)
        except AuthError:
            return AuthCapabilities(login_supported=False, mode="unavailable")
        return AuthCapabilities(login_supported=True, mode="local_session")
    return AuthCapabilities(login_supported=False, mode=settings.dqa_auth_provider)


@router.get("/me", response_model=AuthMeResponse, response_model_exclude_none=True)
def auth_me(
    request: Request,
    response: Response,
    actor: AuthenticatedActor = Depends(get_current_actor),
) -> AuthMeResponse:
    """Return current server-verified identity; CSRF secret is session-bound."""
    response.headers["Cache-Control"] = "no-store"
    csrf = None
    if actor.provider == "local_session":
        csrf = csrf_for_token(request.cookies[COOKIE_NAME], get_settings())
    return AuthMeResponse(
        actor_id=actor.actor_id,
        roles=sorted(role.value for role in actor.roles),
        provider=actor.provider,
        display_name=actor.display_name,
        csrf_token=csrf,
    )


@router.post("/login", response_model=LoginResponse)
def auth_login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    """Interactive password exchange; never accepts caller roles or actor IDs."""
    if settings.dqa_auth_provider != "local_session":
        raise _auth_http_error(AuthError(AuthErrorCode.PROVIDER_UNAVAILABLE, "local login unavailable"))
    try:
        validate_local_auth_settings(settings)
        validate_origin(request, settings)
        password = body.password.get_secret_value()
        if not 1 <= len(password) <= 128:
            raise AuthError(AuthErrorCode.AUTHENTICATION_INVALID, "invalid username or password")
        token = login_with_password(body.username, password)
    except AuthError as exc:
        raise _auth_http_error(exc) from None
    response.set_cookie(
        key=COOKIE_NAME, value=token, max_age=int(SESSION_TTL.total_seconds()),
        path="/api/v1", httponly=True, secure=settings.dqa_local_auth_cookie_secure,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(authenticated=True, csrf_token=csrf_for_token(token, settings))


@router.post("/logout")
def auth_logout(
    request: Request,
    response: Response,
    actor: AuthenticatedActor = Depends(get_current_actor),
) -> dict[str, bool]:
    if actor.provider != "local_session":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail={"code": AuthErrorCode.AUTHORIZATION_DENIED, "message": "local logout unavailable"})
    try:
        revoke_session(request.cookies[COOKIE_NAME])
    except AuthError as exc:
        raise _auth_http_error(exc) from None
    response.delete_cookie(COOKIE_NAME, path="/api/v1")
    response.headers["Cache-Control"] = "no-store"
    return {"authenticated": False}
