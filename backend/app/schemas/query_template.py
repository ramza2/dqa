"""Pydantic schemas for Query Template draft registry APIs."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ParameterType = Literal[
    "string",
    "integer",
    "decimal",
    "boolean",
    "date",
    "datetime",
    "enum",
    "string_list",
    "integer_list",
]

CompatibilityMode = Literal["EXACT_FINGERPRINT"]
ApprovalStatus = Literal["DRAFT", "IN_REVIEW", "APPROVED", "REJECTED"]

PARAM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
STABLE_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


class QueryTemplateParameter(BaseModel):
    """One declared template parameter (structural validation only)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str | None = None
    description: str | None = None
    type: ParameterType
    required: bool = True
    default: Any | None = None
    allowed_values: list[Any] | None = None
    pattern: str | None = None
    min: int | float | Decimal | None = None
    max: int | float | Decimal | None = None
    min_items: int | None = None
    max_items: int | None = None
    sensitive: bool = False

    @field_validator("name")
    @classmethod
    def name_must_be_identifier(cls, value: str) -> str:
        if not isinstance(value, str) or not PARAM_NAME_RE.fullmatch(value):
            raise ValueError("parameter name must be a valid identifier")
        return value

    @model_validator(mode="after")
    def validate_type_constraints(self) -> QueryTemplateParameter:
        if self.min is not None or self.max is not None:
            if self.type not in {"integer", "decimal"}:
                raise ValueError("min/max apply only to integer or decimal parameters")
            if self.min is not None and self.max is not None and self.min > self.max:
                raise ValueError("parameter min must not be greater than max")

        if self.min_items is not None or self.max_items is not None:
            if self.type not in {"string_list", "integer_list"}:
                raise ValueError("min_items/max_items apply only to list parameter types")
            if self.min_items is not None and self.min_items < 0:
                raise ValueError("parameter min_items must be >= 0")
            if self.max_items is not None and self.max_items < 0:
                raise ValueError("parameter max_items must be >= 0")
            if (
                self.min_items is not None
                and self.max_items is not None
                and self.min_items > self.max_items
            ):
                raise ValueError("parameter min_items must not be greater than max_items")

        if self.pattern is not None:
            if self.type != "string":
                raise ValueError("pattern applies only to string parameters")
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"parameter pattern is not a valid regex: {exc}") from exc

        if self.allowed_values is not None:
            if self.type != "enum":
                raise ValueError("allowed_values applies only to enum parameters")
            if not self.allowed_values:
                raise ValueError("enum parameters require a non-empty allowed_values list")
            seen: list[Any] = []
            for value in self.allowed_values:
                if any(_values_equal(value, prior) for prior in seen):
                    raise ValueError("enum allowed_values must not contain duplicates")
                seen.append(value)
        elif self.type == "enum":
            raise ValueError("enum parameters require a non-empty allowed_values list")

        if self.default is not None:
            _assert_default_matches_type(self)

        return self


def _values_equal(left: Any, right: Any) -> bool:
    return left == right and type(left) is type(right)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float, Decimal))


def _assert_default_matches_type(param: QueryTemplateParameter) -> None:
    value = param.default
    param_type = param.type

    if param_type == "string":
        if not isinstance(value, str):
            raise ValueError("string default must be a string")
        return
    if param_type == "integer":
        if not _is_int(value):
            raise ValueError("integer default must be an integer")
        return
    if param_type == "decimal":
        if not _is_number(value):
            raise ValueError("decimal default must be a number")
        return
    if param_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("boolean default must be a boolean")
        return
    if param_type == "date":
        if isinstance(value, date) and not isinstance(value, datetime):
            return
        if isinstance(value, str):
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("date default must be an ISO date string") from exc
            return
        raise ValueError("date default must be an ISO date string")
    if param_type == "datetime":
        if isinstance(value, datetime):
            return
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("datetime default must be an ISO datetime string") from exc
            return
        raise ValueError("datetime default must be an ISO datetime string")
    if param_type == "enum":
        allowed = param.allowed_values or []
        if not any(_values_equal(value, item) for item in allowed):
            raise ValueError("enum default must be one of allowed_values")
        return
    if param_type == "string_list":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError("string_list default must be a list of strings")
        return
    if param_type == "integer_list":
        if not isinstance(value, list) or not all(_is_int(item) for item in value):
            raise ValueError("integer_list default must be a list of integers")
        return

    raise ValueError(f"unsupported parameter type for default: {param_type}")


class QueryTemplateCompatibilityView(BaseModel):
    """Pinned vs current Active Catalog compatibility (read-only view)."""

    model_config = ConfigDict(extra="forbid")

    mode: CompatibilityMode
    compatible: bool
    pinned_revision_id: int
    pinned_schema_fingerprint: str
    current_revision_id: int | None = None
    current_schema_fingerprint: str | None = None


class QueryTemplateVersionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    version: int
    sql_text: str
    parameter_schema: list[QueryTemplateParameter]
    row_limit: int
    timeout_seconds: int
    approval_status: ApprovalStatus
    compatibility: QueryTemplateCompatibilityView
    created_by: str | None = None
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    approval_note: str | None = None


class QueryTemplateSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    stable_key: str
    name: str
    description: str | None = None
    source_name: str
    target_schemas: list[str]
    enabled: bool
    current_version_id: int | None
    current_version: int | None
    approval_status: ApprovalStatus | None
    compatibility: QueryTemplateCompatibilityView | None = None
    created_at: datetime
    updated_at: datetime


class QueryTemplateDetail(QueryTemplateSummary):
    version: QueryTemplateVersionView


class QueryTemplateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int
    limit: int
    offset: int
    items: list[QueryTemplateSummary]


class QueryTemplateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stable_key: str
    name: str
    description: str | None = None
    source_name: str
    target_schemas: list[str] = Field(min_length=1)
    sql_text: str
    parameter_schema: list[QueryTemplateParameter] = Field(default_factory=list)
    row_limit: int = Field(default=100, gt=0)
    timeout_seconds: int = Field(default=30, gt=0)

    @field_validator("stable_key")
    @classmethod
    def validate_stable_key(cls, value: str) -> str:
        if not STABLE_KEY_RE.fullmatch(value):
            raise ValueError("stable_key must start with a letter and use [A-Za-z0-9_.-]")
        return value

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @field_validator("source_name")
    @classmethod
    def source_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("source_name must not be blank")
        return cleaned

    @field_validator("sql_text")
    @classmethod
    def sql_not_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("sql_text must not be blank")
        return value

    @field_validator("target_schemas")
    @classmethod
    def schemas_not_blank(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("target_schemas must not be empty")
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("target_schemas entries must be non-blank strings")
            name = item.strip()
            key = name.casefold()
            if key in seen:
                raise ValueError(f"duplicate target schema: {name}")
            seen.add(key)
            cleaned.append(name)
        return cleaned

    @field_validator("parameter_schema")
    @classmethod
    def unique_parameter_names(
        cls, value: list[QueryTemplateParameter]
    ) -> list[QueryTemplateParameter]:
        seen: set[str] = set()
        for param in value:
            key = param.name.casefold()
            if key in seen:
                raise ValueError(f"duplicate parameter name: {param.name}")
            seen.add(key)
        return value


class QueryTemplateUpdateRequest(BaseModel):
    """Authoring fields for the current DRAFT version. Source/fingerprint are immutable."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    target_schemas: list[str] | None = None
    sql_text: str | None = None
    parameter_schema: list[QueryTemplateParameter] | None = None
    row_limit: int | None = Field(default=None, gt=0)
    timeout_seconds: int | None = Field(default=None, gt=0)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name must not be blank")
        return cleaned

    @field_validator("sql_text")
    @classmethod
    def sql_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("sql_text must not be blank")
        return value

    @field_validator("target_schemas")
    @classmethod
    def schemas_not_blank(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("target_schemas must not be empty")
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("target_schemas entries must be non-blank strings")
            name = item.strip()
            key = name.casefold()
            if key in seen:
                raise ValueError(f"duplicate target schema: {name}")
            seen.add(key)
            cleaned.append(name)
        return cleaned

    @field_validator("parameter_schema")
    @classmethod
    def unique_parameter_names(
        cls, value: list[QueryTemplateParameter] | None
    ) -> list[QueryTemplateParameter] | None:
        if value is None:
            return value
        seen: set[str] = set()
        for param in value:
            key = param.name.casefold()
            if key in seen:
                raise ValueError(f"duplicate parameter name: {param.name}")
            seen.add(key)
        return value

    @model_validator(mode="after")
    def at_least_one_field(self) -> QueryTemplateUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self
