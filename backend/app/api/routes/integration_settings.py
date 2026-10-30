"""Administrator-only, secret-free integration settings status.

M5-S0 inventory: this is not a credential-management API, LLM enable switch,
or an external-service authentication provider. No outbound requests occur.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.core.config import Settings, get_settings
from app.services.llm_connection_probe import (
    LLMConnectionTestResult,
    llm_connection_test_available,
    probe_configured_llm,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-integrations"])


class LLMStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = "openai_compatible"
    endpoint_configured: bool
    model_configured: bool
    model: str | None
    api_key_present: bool
    raw_request_egress_allowed: bool
    connection_test_available: bool


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
