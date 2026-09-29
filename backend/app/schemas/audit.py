"""Schemas for Query Audit Event read API and internal append-only writes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

AuditEventType = Literal["QUERY_REQUEST", "QUERY_EXECUTION"]
AuditStatus = Literal["STARTED", "SUCCEEDED", "FAILED", "DENIED"]
ParameterLoggingPolicy = Literal["NAMES_ONLY"]

MAX_AUDIT_ID_LENGTH = 64
MAX_ACTOR_ID_LENGTH = 255
MAX_SOURCE_NAME_LENGTH = 255
MAX_FINGERPRINT_LENGTH = 128
MAX_FAILURE_CATEGORY_LENGTH = 64
MAX_PARAMETER_NAME_LENGTH = 128
MAX_PARAMETER_NAMES = 64

ALLOWED_EVENT_TYPES = frozenset({"QUERY_REQUEST", "QUERY_EXECUTION"})
ALLOWED_STATUSES = frozenset({"STARTED", "SUCCEEDED", "FAILED", "DENIED"})


class QueryAuditEventCreate(BaseModel):
    """Internal append-only write payload.

    Intentionally omits parameter values, SQL, request_text, result rows,
    exception bodies, and credentials so callers cannot pass them through
    this contract (``extra=\"forbid\"``).
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    audit_id: str | None = Field(default=None, max_length=MAX_AUDIT_ID_LENGTH)
    event_type: AuditEventType
    status: AuditStatus
    actor_id: str | None = Field(default=None, max_length=MAX_ACTOR_ID_LENGTH)
    source_name: str | None = Field(default=None, max_length=MAX_SOURCE_NAME_LENGTH)
    catalog_revision_id: int | None = Field(default=None, gt=0)
    catalog_fingerprint: str | None = Field(default=None, max_length=MAX_FINGERPRINT_LENGTH)
    template_id: int | None = Field(default=None, gt=0)
    template_version_id: int | None = Field(default=None, gt=0)
    connection_profile_id: int | None = Field(default=None, gt=0)
    parameter_names: list[str] = Field(default_factory=list, max_length=MAX_PARAMETER_NAMES)
    sensitive_parameter_names: list[str] = Field(
        default_factory=list, max_length=MAX_PARAMETER_NAMES
    )
    failure_category: str | None = Field(default=None, max_length=MAX_FAILURE_CATEGORY_LENGTH)
    elapsed_ms: int | None = Field(default=None, ge=0)
    row_count: int | None = Field(default=None, ge=0)
    result_truncated: bool | None = Field(default=None, strict=True)

    @field_validator("audit_id", "actor_id", "source_name", "catalog_fingerprint")
    @classmethod
    def optional_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("failure_category")
    @classmethod
    def sanitized_optional_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        # Bound token: letters, digits, underscore, hyphen, slash only.
        for ch in cleaned:
            if not (ch.isalnum() or ch in {"_", "-", "/"}):
                raise ValueError("must be a sanitized token")
        return cleaned

    @field_validator("parameter_names", "sensitive_parameter_names")
    @classmethod
    def normalize_name_list(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in values:
            if not isinstance(raw, str):
                raise ValueError("parameter names must be strings")
            name = raw.strip()
            if not name:
                continue
            if len(name) > MAX_PARAMETER_NAME_LENGTH:
                raise ValueError("parameter name exceeds maximum length")
            if name in seen:
                continue
            seen.add(name)
            normalized.append(name)
        if len(normalized) > MAX_PARAMETER_NAMES:
            raise ValueError("too many parameter names")
        return normalized


def new_audit_id() -> str:
    """Generate a new application audit correlation id."""
    return str(uuid4())


class QueryAuditEventView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    audit_id: str
    event_type: AuditEventType
    status: AuditStatus
    actor_id: str | None = None
    source_name: str | None = None
    catalog_revision_id: int | None = None
    catalog_fingerprint: str | None = None
    template_id: int | None = None
    template_version_id: int | None = None
    connection_profile_id: int | None = None
    parameter_names: list[str] = Field(default_factory=list)
    sensitive_parameter_names: list[str] = Field(default_factory=list)
    parameter_logging_policy: ParameterLoggingPolicy
    failure_category: str | None = None
    elapsed_ms: int | None = None
    row_count: int | None = None
    result_truncated: bool | None = Field(default=None, strict=True)
    created_at: datetime


class QueryAuditEventListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    limit: int
    offset: int
    items: list[QueryAuditEventView]
