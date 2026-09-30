"""Validated Connection Profile snapshot for DEMIS adapter factory input."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_NAME_LENGTH = 255
MAX_SOURCE_NAME_LENGTH = 255
MAX_ENVIRONMENT_LENGTH = 64
MAX_DBMS_TYPE_LENGTH = 64
MAX_HOST_LENGTH = 255
MAX_DATABASE_NAME_LENGTH = 255
MAX_USERNAME_LENGTH = 255
MAX_CREDENTIAL_SECRET_REF_LENGTH = 512


class ConnectionProfileSnapshot(BaseModel):
    """Non-ORM snapshot of Connection Profile configuration for adapter factory.

    Carries source/environment binding and non-secret target metadata plus a
    credential *reference*. Never carries resolved secret values.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    profile_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=MAX_NAME_LENGTH)
    source_name: str = Field(min_length=1, max_length=MAX_SOURCE_NAME_LENGTH)
    environment: str = Field(min_length=1, max_length=MAX_ENVIRONMENT_LENGTH)
    enabled: bool
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
        return cleaned or None

    def sanitized_label(self) -> str:
        """Safe identifier for logs/errors (no host/user/credentials)."""
        return (
            f"profile_id={self.profile_id} "
            f"source={self.source_name} env={self.environment}"
        )
