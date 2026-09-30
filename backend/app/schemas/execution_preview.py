"""Schemas for Query Execution preview (no live DEMIS execution)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_SOURCE_NAME_LENGTH = 255
MAX_ENVIRONMENT_LENGTH = 64
# Bound request parameter map size (template parameter_schema is also bounded).
MAX_REQUEST_PARAMETERS = 128

ExecutionBlockerCode = Literal["DEMIS_ADAPTER_UNAVAILABLE"]


class ExecutionPreviewRequest(BaseModel):
    """Caller-supplied preview input. Authoritative metadata is loaded server-side."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(min_length=1, max_length=MAX_SOURCE_NAME_LENGTH)
    environment: str = Field(min_length=1, max_length=MAX_ENVIRONMENT_LENGTH)
    template_id: int = Field(gt=0)
    version_id: int = Field(gt=0)
    parameters: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_name", "environment")
    @classmethod
    def required_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("parameters")
    @classmethod
    def bound_parameter_map(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(value) > MAX_REQUEST_PARAMETERS:
            raise ValueError(
                f"parameters must contain at most {MAX_REQUEST_PARAMETERS} entries"
            )
        return value


class ExecutionPreviewResponse(BaseModel):
    """Deterministic preview for operator confirmation before future execution."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    environment: str
    catalog_revision_id: int
    catalog_fingerprint: str
    template_id: int
    version_id: int
    version: int
    connection_profile_id: int
    resolved_parameters: dict[str, Any]
    sensitive_parameter_names: list[str]
    row_limit: int
    timeout_seconds: int
    execution_available: bool
    execution_blockers: list[ExecutionBlockerCode] = Field(default_factory=list)
