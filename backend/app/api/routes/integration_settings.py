"""Administrator-only integration settings and dev-gated LLM diagnostic.

The M5-S0 inventory makes no outbound requests. The separate development-only
POST may probe the pinned model-list endpoint; neither manages credentials,
enables provider usage, nor authorizes data egress or external service access.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.core.config import Settings, get_settings
from app.services.llm_connection_candidate import (
    LLMConnectionCandidateDecision,
    _validated_endpoint,
    assess_llm_connection_candidate,
)
from app.services.llm_connection_probe import (
    LLMConnectionTestResult,
    llm_connection_test_available,
    probe_configured_llm,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-integrations"])

MAX_CANDIDATE_REVIEW_BODY_BYTES = 4096


def llm_candidate_review_available(settings: Settings) -> bool:
    """Explicit dev/test opt-in and exactly one well-formed HTTPS URL pin."""

    if settings.app_env not in {"development", "test"}:
        return False
    if not settings.dqa_dev_llm_candidate_review_enabled:
        return False
    approved = settings.dqa_dev_llm_candidate_review_allowed_base_url or ""
    normalized, error = _validated_endpoint(approved)
    return error is None and normalized is not None


def _unique_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Duplicate JSON keys are ambiguous and must fail closed."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate json field")
        result[key] = value
    return result



class LLMStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "openai_compatible"
    endpoint_configured: bool
    model_configured: bool
    model: str | None
    api_key_present: bool
    raw_request_egress_allowed: bool
    connection_test_available: bool
    candidate_review_available: bool = False


class ExternalServiceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_client_management_available: bool = False
    managed_service_authentication_available: bool = False


class IntegrationSettingsStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    llm: LLMStatus
    external_service: ExternalServiceStatus
    editable: bool = False


@router.get("/integration-settings", response_model=IntegrationSettingsStatus)
def get_integration_settings_status(
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
    settings: Settings = Depends(get_settings),
) -> IntegrationSettingsStatus:
    """Return the safe configuration inventory without resolving secrets.

    An LLM endpoint being configured is not equivalent to an approved data
    egress policy. Service-client authentication is not implemented yet.
    """
    base_url_present = bool((settings.llm_base_url or "").strip())
    model = (settings.llm_model or "").strip() or None
    api_key_present = bool(
        settings.llm_api_key and settings.llm_api_key.get_secret_value()
    )
    return IntegrationSettingsStatus(
        llm=LLMStatus(
            endpoint_configured=base_url_present,
            model_configured=model is not None,
            model=model,
            api_key_present=api_key_present,
            connection_test_available=llm_connection_test_available(settings),
            candidate_review_available=llm_candidate_review_available(settings),
            raw_request_egress_allowed=(
                settings.llm_parameter_extraction_allow_raw_request
                and settings.llm_parameter_extraction_raw_request_egress_approved
            ),
        ),
        external_service=ExternalServiceStatus(),
    )


@router.post(
    "/integration-settings/llm/test",
    response_model=LLMConnectionTestResult,
)
def test_configured_llm_connection(
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
    settings: Settings = Depends(get_settings),
) -> LLMConnectionTestResult:
    """Dev-only GET /v1/models via pinned configuration, with no user URL/body.

    This diagnostic never posts prompts, SQL, query rows, or clinical data.
    It is intentionally not a runtime provider enable or egress authorization.
    """
    if not llm_connection_test_available(settings):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "LLM_CONNECTION_TEST_DISABLED",
                "message": "LLM connection test is not available",
            },
        )
    return probe_configured_llm(settings)


@router.post(
    "/integration-settings/llm-candidate/review",
    response_model=LLMConnectionCandidateDecision,
)
async def review_llm_connection_candidate(
    request: Request,
    _actor: AuthenticatedActor = Depends(
        require_permission(Permission.CONNECTION_PROFILE_MANAGE)
    ),
    settings: Settings = Depends(get_settings),
) -> LLMConnectionCandidateDecision:
    """Dev-only stateless candidate syntax/pin review, never a connection probe.

    No user-provided URL is contacted. Do not add DB, secrets, audit mutations
    or activation side effects to this diagnostic endpoint.
    """
    if not llm_candidate_review_available(settings):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "LLM_CANDIDATE_REVIEW_DISABLED",
                "message": "LLM candidate review is unavailable",
            },
        )

    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(
            status_code=415,
            detail={"code": "JSON_BODY_REQUIRED", "message": "JSON body required"},
        )

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_CANDIDATE_REVIEW_BODY_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"code": "CANDIDATE_BODY_TOO_LARGE", "message": "Body too large"},
            )
        chunks.append(chunk)

    try:
        candidate = json.loads(b"".join(chunks), object_pairs_hook=_unique_json_keys)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return LLMConnectionCandidateDecision(code="INVALID_FIELDS")

    if not isinstance(candidate, dict):
        return LLMConnectionCandidateDecision(code="INVALID_FIELDS")

    return assess_llm_connection_candidate(
        candidate,
        allowed_base_urls=(
            settings.dqa_dev_llm_candidate_review_allowed_base_url or "",
        ),
    )
