"""M5-S1A strictly non-authorizing service client registration contracts."""

from __future__ import annotations

import ipaddress
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_NAME = re.compile(r"^[a-z][a-z0-9._-]{2,63}$")
_SCOPE = re.compile(r"^[a-z][a-z0-9:._-]{1,63}$")


class ServiceClientDraftCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    client_id: str = Field(min_length=3, max_length=64)
    service_name: str = Field(min_length=1, max_length=128)
    organization: str = Field(min_length=1, max_length=128)
    owner_contact: str = Field(min_length=1, max_length=128)
    purpose: str = Field(min_length=1, max_length=255)
    environment: Literal["development", "test", "production"]
    requested_scopes: list[str] = Field(default_factory=list, max_length=32)
    proposed_ip_cidrs: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("client_id")
    @classmethod
    def valid_client_id(cls, value: str) -> str:
        if not _NAME.fullmatch(value):
            raise ValueError("invalid client ID format")
        return value

    @field_validator("requested_scopes")
    @classmethod
    def valid_scopes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not _SCOPE.fullmatch(item) for item in value):
            raise ValueError("invalid or duplicate requested scope")
        return sorted(value)

    @field_validator("proposed_ip_cidrs")
    @classmethod
    def valid_cidrs(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            try:
                network = ipaddress.ip_network(item, strict=False)
            except ValueError as exc:
                raise ValueError("invalid IP/CIDR") from exc
            if network.prefixlen == 0:
                raise ValueError("unrestricted networks are not permitted")
            normalized.append(str(network))
        if len(normalized) != len(set(normalized)):
            raise ValueError("duplicate IP/CIDR")
        return sorted(normalized)


class ServiceClientDraftPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service_name: str | None = Field(default=None, min_length=1, max_length=128)
    organization: str | None = Field(default=None, min_length=1, max_length=128)
    owner_contact: str | None = Field(default=None, min_length=1, max_length=128)
    purpose: str | None = Field(default=None, min_length=1, max_length=255)
    requested_scopes: list[str] | None = Field(default=None, max_length=32)
    proposed_ip_cidrs: list[str] | None = Field(default=None, max_length=32)

    @field_validator("requested_scopes")
    @classmethod
    def valid_scopes(cls, value: list[str] | None) -> list[str] | None:
        return ServiceClientDraftCreate.valid_scopes(value) if value is not None else None

    @field_validator("proposed_ip_cidrs")
    @classmethod
    def valid_cidrs(cls, value: list[str] | None) -> list[str] | None:
        return ServiceClientDraftCreate.valid_cidrs(value) if value is not None else None

    @model_validator(mode="after")
    def require_non_null_patch(self) -> "ServiceClientDraftPatch":
        if not self.model_fields_set or any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("at least one non-null patch field is required")
        return self


class ServiceClientDraftView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    client_id: str
    service_name: str
    organization: str
    owner_contact: str
    purpose: str
    environment: str
    requested_scopes: list[str]
    proposed_ip_cidrs: list[str]
    status: Literal["DRAFT", "REVOKED"]
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None
    authentication_enabled: bool = False
    external_access_allowed: bool = False


class ServiceClientDraftList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    items: list[ServiceClientDraftView]


class ServiceClientDraftEventView(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    action: Literal["CREATED", "UPDATED", "REVOKED"]
    actor_id: str
    changed_fields: list[str]
    policy_sha256: str
    occurred_at: datetime
