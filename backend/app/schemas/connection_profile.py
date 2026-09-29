"""Pydantic schemas for Connection Profile management APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_NAME_LENGTH = 255
MAX_SOURCE_NAME_LENGTH = 255
MAX_ENVIRONMENT_LENGTH = 64
MAX_DBMS_TYPE_LENGTH = 64
MAX_HOST_LENGTH = 255
MAX_DATABASE_NAME_LENGTH = 255
MAX_USERNAME_LENGTH = 255
MAX_CREDENTIAL_SECRET_REF_LENGTH = 512


class ConnectionProfileCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    source_name: str = Field(min_length=1, max_length=MAX_SOURCE_NAME_LENGTH)
    environment: str = Field(min_length=1, max_length=MAX_ENVIRONMENT_LENGTH)
    dbms_type: str | None = Field(default=None, max_length=MAX_DBMS_TYPE_LENGTH)
    host: str | None = Field(default=None, max_length=MAX_HOST_LENGTH)
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = Field(default=None, max_length=MAX_DATABASE_NAME_LENGTH)
    username: str | None = Field(default=None, max_length=MAX_USERNAME_LENGTH)
    credential_secret_ref: str | None = Field(
        default=None, max_length=MAX_CREDENTIAL_SECRET_REF_LENGTH
    )

    @field_validator("name", "source_name", "environment")
    @classmethod
    def required_non_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator(
        "dbms_type",
        "host",
        "database_name",
        "username",
        "credential_secret_ref",
    )
    @classmethod
    def optional_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned


class ConnectionProfileUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=MAX_NAME_LENGTH)
    dbms_type: str | None = Field(default=None, max_length=MAX_DBMS_TYPE_LENGTH)
    host: str | None = Field(default=None, max_length=MAX_HOST_LENGTH)
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = Field(default=None, max_length=MAX_DATABASE_NAME_LENGTH)
    username: str | None = Field(default=None, max_length=MAX_USERNAME_LENGTH)
    credential_secret_ref: str | None = Field(
        default=None, max_length=MAX_CREDENTIAL_SECRET_REF_LENGTH
    )

    @model_validator(mode="after")
    def at_least_one_field(self) -> ConnectionProfileUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self

    @field_validator("name")
    @classmethod
    def name_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator(
        "dbms_type",
        "host",
        "database_name",
        "username",
        "credential_secret_ref",
    )
    @classmethod
    def optional_non_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned


class ConnectionProfileView(BaseModel):
    """Management view: non-secret metadata + credential reference only."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    source_name: str
    environment: str
    enabled: bool
    dbms_type: str | None = None
    host: str | None = None
    port: int | None = None
    database_name: str | None = None
    username: str | None = None
    credential_secret_ref: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ConnectionProfileListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    limit: int
    offset: int
    items: list[ConnectionProfileView]


DiagnosticsStatus = Literal[
    "INCOMPLETE",
    "CONFIGURED_DISABLED",
    "CONFIGURED_ENABLED",
]


class ConnectionProfileDiagnosticsIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ConnectionProfileDiagnosticsResponse(BaseModel):
    """Configuration-level sanitized diagnostics (no live DEMIS connection)."""

    model_config = ConfigDict(extra="forbid")

    profile_id: int
    source_name: str
    environment: str
    enabled: bool
    credential_reference_configured: bool
    target_metadata_configured: bool
    status: DiagnosticsStatus
    issues: list[ConnectionProfileDiagnosticsIssue] = Field(default_factory=list)
    # Explicitly documents that live connectivity was not tested.
    live_connection_tested: bool = False
