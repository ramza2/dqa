"""M5-L1B: pure, fail-closed review of proposed LLM connection metadata.

No database, secret access, DNS resolution, HTTP calls, provider construction,
active runtime reconfiguration, or permission/egress grant is performed here.
A matching operator allowlist is necessary but never sufficient for activation.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

ConnectionEnvironment = Literal["modelops", "snuh_ai", "self_hosted", "other"]
ConnectionProtocol = Literal["openai_compatible", "custom_api"]
DecisionCode = Literal[
    "INVALID_FIELDS",
    "INSECURE_ENDPOINT",
    "INVALID_ENDPOINT",
    "UNSUPPORTED_ADAPTER",
    "ENDPOINT_NOT_ALLOWLISTED",
    "POLICY_REVIEW_REQUIRED",
]


class LLMConnectionCandidate(BaseModel):
    """Untrusted candidate form; never an enabled or approved runtime profile."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    environment: ConnectionEnvironment
    protocol: ConnectionProtocol
    base_url: str = Field(alias="baseUrl", min_length=1, max_length=2048)
    model_id: str = Field(alias="modelId", min_length=1, max_length=200)
    timeout_seconds: int = Field(
        default=60, alias="timeoutSeconds", ge=1, le=300, strict=True
    )

    @field_validator("name", "model_id")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(ord(character) < 33 or ord(character) == 127 for character in value):
            raise ValueError("invalid identifier")
        return value


class LLMConnectionCandidateDecision(BaseModel):
    """Only sanitized policy state; never reflect user-provided host or secrets."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: DecisionCode
    server_configuration_changed: Literal[False] = False
    credential_loaded: Literal[False] = False
    ready_for_runtime: Literal[False] = False
    ready_for_connection_test: Literal[False] = False


def _validated_endpoint(value: str) -> tuple[str | None, DecisionCode | None]:
    """Normalize only trivial trailing slash; disallow URL parser ambiguities."""

    raw = value.strip()
    if (
        not raw
        or len(raw) > 2048
        or any(ord(c) < 33 or ord(c) == 127 for c in raw)
        or "\\" in raw
    ):
        return None, "INVALID_ENDPOINT"

    try:
        parts = urlsplit(raw)
        _ = parts.port
        if parts.scheme != "https":
            return None, "INSECURE_ENDPOINT"
        if (
            not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or "%" in parts.netloc
            or "%" in parts.path
            or ";" in parts.path
            or "//" in parts.path
            or any(segment in {".", ".."} for segment in parts.path.split("/"))
            or (parts.port is not None and parts.port < 1)
        ):
            return None, "INVALID_ENDPOINT"
    except ValueError:
        return None, "INVALID_ENDPOINT"

    # No automatic cross-origin or alternate-port equivalence.
    # A custom API path is allowed as an *unusable draft* until an adapter exists.
    return raw[:-1] if raw.endswith("/") else raw, None


def assess_llm_connection_candidate(
    payload: Mapping[str, Any],
    *,
    allowed_base_urls: Iterable[str] = (),
) -> LLMConnectionCandidateDecision:
    """Review candidate fields against operator-provided exact HTTPS URL pins.

    Never grant model execution or connection testing based on this decision.
    A future live URL check must independently handle DNS rebind, redirects,
    network ACLs, admin identity, secrets and institutional approval.
    """

    try:
        draft = LLMConnectionCandidate.model_validate(payload)
    except (ValidationError, ValueError, TypeError):
        return LLMConnectionCandidateDecision(code="INVALID_FIELDS")

    endpoint, error = _validated_endpoint(draft.base_url)
    if error is not None:
        return LLMConnectionCandidateDecision(code=error)
    assert endpoint is not None

    if draft.protocol != "openai_compatible":
        return LLMConnectionCandidateDecision(code="UNSUPPORTED_ADAPTER")

    allowed: set[str] = set()
    for item in allowed_base_urls:
        if not isinstance(item, str):
            continue
        normalized, invalid = _validated_endpoint(item)
        if invalid is None and normalized is not None:
            allowed.add(normalized)

    if endpoint not in allowed:
        return LLMConnectionCandidateDecision(code="ENDPOINT_NOT_ALLOWLISTED")

    return LLMConnectionCandidateDecision(code="POLICY_REVIEW_REQUIRED")
