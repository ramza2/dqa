"""Pydantic contracts for Structured Query Plans (Phase 29-B).

Plans are validation-only logical descriptions. They are not SQL, not execution
tokens, and not approved/executable production authority.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.structured_query_plan import (
    MAX_AGGREGATIONS,
    MAX_FILTERS,
    MAX_GROUP_BY_FIELDS,
    MAX_LIMIT,
    MAX_RELATIONSHIPS,
    MAX_SELECT_FIELDS,
    MAX_SORT_SPECS,
    MIN_LIMIT,
    PLAN_FORMAT_VERSION,
    AggregationFunction,
    FilterOperator,
    PlanIssueCode,
    PlanValidationStatus,
    SortDirection,
)

FilterOperatorLiteral = Literal[
    "EQ",
    "NE",
    "LT",
    "LE",
    "GT",
    "GE",
    "IN",
    "NOT_IN",
    "BETWEEN",
    "LIKE",
    "IS_NULL",
    "IS_NOT_NULL",
]
SortDirectionLiteral = Literal["ASC", "DESC"]
AggregationFunctionLiteral = Literal["COUNT", "SUM", "AVG", "MIN", "MAX"]
PlanStatusLiteral = Literal["VALID", "INVALID", "NOT_CONFIGURED", "STALE"]

_FIELD_KEY_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"
_RESOURCE_KEY_PATTERN = r"^[A-Za-z][A-Za-z0-9_.]*$"
_RELATIONSHIP_KEY_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*$"


class PlanFilterPredicate(BaseModel):
    """One typed filter predicate — no arbitrary expression/SQL text."""

    model_config = ConfigDict(extra="forbid")

    field_key: str = Field(min_length=1, max_length=255, pattern=_FIELD_KEY_PATTERN)
    operator: FilterOperator | FilterOperatorLiteral
    # Scalar, list (IN/BETWEEN), or null (IS_NULL / IS_NOT_NULL).
    value: Any = None

    @field_validator("operator", mode="before")
    @classmethod
    def coerce_operator(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PlanSortSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_key: str = Field(min_length=1, max_length=255, pattern=_FIELD_KEY_PATTERN)
    direction: SortDirection | SortDirectionLiteral = SortDirection.ASC

    @field_validator("direction", mode="before")
    @classmethod
    def coerce_direction(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class PlanAggregationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    function: AggregationFunction | AggregationFunctionLiteral
    field_key: str = Field(min_length=1, max_length=255, pattern=_FIELD_KEY_PATTERN)
    alias: str | None = Field(
        default=None, min_length=1, max_length=64, pattern=_FIELD_KEY_PATTERN
    )

    @field_validator("function", mode="before")
    @classmethod
    def coerce_function(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class StructuredQueryPlan(BaseModel):
    """Caller-supplied Structured Query Plan (Path B) — validation input only."""

    model_config = ConfigDict(extra="forbid")

    plan_format_version: str = Field(default=PLAN_FORMAT_VERSION, min_length=1, max_length=32)
    source_name: str = Field(min_length=1, max_length=255)
    resource_key: str = Field(
        min_length=1, max_length=255, pattern=_RESOURCE_KEY_PATTERN
    )
    select: list[str] = Field(min_length=1, max_length=MAX_SELECT_FIELDS)
    filters: list[PlanFilterPredicate] = Field(default_factory=list, max_length=MAX_FILTERS)
    sort: list[PlanSortSpec] = Field(default_factory=list, max_length=MAX_SORT_SPECS)
    group_by: list[str] = Field(default_factory=list, max_length=MAX_GROUP_BY_FIELDS)
    aggregations: list[PlanAggregationSpec] = Field(
        default_factory=list, max_length=MAX_AGGREGATIONS
    )
    relationships: list[str] = Field(default_factory=list, max_length=MAX_RELATIONSHIPS)
    limit: int = Field(default=100, ge=MIN_LIMIT, le=MAX_LIMIT)

    @field_validator("select", "group_by")
    @classmethod
    def field_keys_must_be_identifiers(cls, value: list[str]) -> list[str]:
        import re

        pattern = re.compile(_FIELD_KEY_PATTERN)
        for item in value:
            if not pattern.fullmatch(item):
                raise ValueError(f"invalid field_key {item!r}")
        return value

    @field_validator("relationships")
    @classmethod
    def relationship_keys_must_be_identifiers(cls, value: list[str]) -> list[str]:
        import re

        pattern = re.compile(_RELATIONSHIP_KEY_PATTERN)
        for item in value:
            if not pattern.fullmatch(item):
                raise ValueError(f"invalid relationship_key {item!r}")
        return value

    @model_validator(mode="after")
    def reject_empty_select_entries(self) -> StructuredQueryPlan:
        if any(not item.strip() for item in self.select):
            raise ValueError("select entries must be non-empty")
        return self


class PlanValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: PlanIssueCode | str
    message: str
    field_key: str | None = None
    relationship_key: str | None = None


class ValidatedFieldRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_key: str
    data_type: str
    resource_key: str


class ValidatedFilterPredicate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_key: str
    data_type: str
    operator: FilterOperatorLiteral
    value: Any = None


class ValidatedSortSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    field_key: str
    direction: SortDirectionLiteral


class ValidatedAggregationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    function: AggregationFunctionLiteral
    field_key: str
    alias: str | None = None
    data_type: str


class ValidatedLogicalPlan(BaseModel):
    """Immutable validation-only logical plan.

    Never treated as approved or executable production authority. No SQL and
    no execution tokens are produced in Phase 29-B.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    validation_only: Literal[True] = True
    executable: Literal[False] = False
    approved: Literal[False] = False
    status: PlanValidationStatus | PlanStatusLiteral
    plan_format_version: str
    source_name: str
    catalog_revision_id: int | None = None
    schema_fingerprint: str | None = None
    mapping_version: str | None = None
    resource_key: str | None = None
    select: list[ValidatedFieldRef] = Field(default_factory=list)
    filters: list[ValidatedFilterPredicate] = Field(default_factory=list)
    sort: list[ValidatedSortSpec] = Field(default_factory=list)
    group_by: list[ValidatedFieldRef] = Field(default_factory=list)
    aggregations: list[ValidatedAggregationSpec] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    limit: int | None = None
    issues: list[PlanValidationIssue] = Field(default_factory=list)


__all__ = [
    "PlanAggregationSpec",
    "PlanFilterPredicate",
    "PlanSortSpec",
    "PlanValidationIssue",
    "StructuredQueryPlan",
    "ValidatedAggregationSpec",
    "ValidatedFieldRef",
    "ValidatedFilterPredicate",
    "ValidatedLogicalPlan",
    "ValidatedSortSpec",
]
