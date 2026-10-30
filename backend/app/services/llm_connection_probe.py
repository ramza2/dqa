"""Development-only, nonclinical LLM metadata connectivity diagnostic.

No prompt, patient data, query rows or SQL is sent. This is not proof of
provider approval, production availability, or permission for LLM egress.
"""

from __future__ import annotations

import json
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict

from app.core.config import Settings

_MAX_RESPONSE_BYTES = 131072


class LLMConnectionTestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "CONNECTED", "MODEL_NOT_FOUND", "HTTP_ERROR", "TIMEOUT",
        "NETWORK_ERROR", "INVALID_RESPONSE",
    ]
    http_status: int | None = None


def _approved_base_url(value: str | None) -> str | None:
    """Accept only one explicit HTTPS base URL, optionally ending in /v1."""
    raw = (value or "").strip().rstrip("/")
    if not raw or any(c.isspace() for c in raw):
        return None
    try:
        parts = urlsplit(raw)
        if (
            parts.scheme != "https"
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/v1"}
        ):
            return None
        _ = parts.port  # malformed ports fail closed
    except ValueError:
        return None
    return raw


def llm_connection_test_available(settings: Settings) -> bool:
    """Require development/test plus explicit exact-URL operator pinning."""
    if (
        settings.app_env not in {"development", "test"}
        or not settings.dqa_dev_llm_connection_test_enabled
        or not (settings.llm_model or "").strip()
    ):
        return False
    base = _approved_base_url(settings.llm_base_url)
    approved = _approved_base_url(
        settings.dqa_dev_llm_connection_test_allowed_base_url
    )
    return base is not None and base == approved


def probe_configured_llm(
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> LLMConnectionTestResult:
    """GET only the pinned /v1/models endpoint; never expose response content."""
    if not llm_connection_test_available(settings):
        raise ValueError("LLM connection test is disabled")

    base = _approved_base_url(settings.llm_base_url)
    assert base is not None  # re-checked by the gate above
    url = f"{base if base.endswith('/v1') else base + '/v1'}/models"
    headers = {"Accept": "application/json"}
    if settings.llm_api_key:
        key = settings.llm_api_key.get_secret_value().strip()
        if key:
            headers["Authorization"] = f"Bearer {key}"
    timeout = httpx.Timeout(6.0, connect=3.0)
    try:
        with httpx.Client(
            timeout=timeout, transport=transport, trust_env=False,
            follow_redirects=False,
        ) as client:
            with client.stream("GET", url, headers=headers) as response:
                code = response.status_code
                # Redirects are intentionally not followed.
                if code != 200:
                    return LLMConnectionTestResult(
                        status="HTTP_ERROR", http_status=code
                    )
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > _MAX_RESPONSE_BYTES:
                        return LLMConnectionTestResult(
                            status="INVALID_RESPONSE", http_status=200
                        )
    except httpx.TimeoutException:
        return LLMConnectionTestResult(status="TIMEOUT")
    except httpx.HTTPError:
        # Transport exception details can include the host, URL and key.
        return LLMConnectionTestResult(status="NETWORK_ERROR")

    try:
        body = json.loads(chunks)
        data = body["data"]
        if not isinstance(data, list) or not all(
            isinstance(item, dict) and isinstance(item.get("id"), str)
            for item in data
        ):
            raise ValueError("invalid model list")
    except (ValueError, TypeError, KeyError):
        return LLMConnectionTestResult(
            status="INVALID_RESPONSE", http_status=200
        )
    configured_model = (settings.llm_model or "").strip()
    return LLMConnectionTestResult(
        status=(
            "CONNECTED"
            if any(item["id"] == configured_model for item in data)
            else "MODEL_NOT_FOUND"
        ),
        http_status=200,
    )
