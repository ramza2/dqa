"""Schemas for Query Template parameter extraction (no SQL execution)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_SOURCE_NAME_LENGTH = 255
MAX_EXTRACTION_REQUEST_TEXT_CHARS = 2000
MAX_EXTRACTION_PARAMETER_DESCRIPTION_CHARS = 500
MAX_EXTRACTION_PARAMETER_LABEL_CHARS = 200
MAX_EXTRACTION_PROMPT_USER_JSON_CHARS = 12_000
PARAMETER_EXTRACTION_MAX_TOKENS = 1024
MAX_EXTRACTION_CLARIFICATION_CHARS = 500
MAX_CLARIFICATION_PARAMETER_NAMES = 8

# Clarification / validation issue codes (HTTP 200 workflow outcomes).
ISSUE_MISSING_REQUIRED = "MISSING_REQUIRED"
ISSUE_UNRESOLVED = "UNRESOLVED"
ISSUE_TYPE_MISMATCH = "TYPE_MISMATCH"
ISSUE_PATTERN_MISMATCH = "PATTERN_MISMATCH"
ISSUE_MIN_VIOLATION = "MIN_VIOLATION"
ISSUE_MAX_VIOLATION = "MAX_VIOLATION"
ISSUE_ENUM_NOT_ALLOWED = "ENUM_NOT_ALLOWED"
ISSUE_MIN_ITEMS_VIOLATION = "MIN_ITEMS_VIOLATION"
ISSUE_MAX_ITEMS_VIOLATION = "MAX_ITEMS_VIOLATION"


class ParameterExtractionRequest(BaseModel):
    """Extract declared parameter values for one eligible Query Template version."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(min_length=1, max_length=MAX_SOURCE_NAME_LENGTH)
    template_id: int = Field(gt=0)
    version_id: int = Field(gt=0)
    request_text: str = Field(min_length=1, max_length=MAX_EXTRACTION_REQUEST_TEXT_CHARS)

    @field_validator("source_name", "request_text")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class ParameterExtractionIssueView(BaseModel):
    """One deterministic clarification/validation issue (no parameter values)."""

    model_config = ConfigDict(extra="forbid")

    parameter_name: str
    code: str
    message: str


class ParameterExtractionResponse(BaseModel):
    """Extraction / clarification outcome (not execution permission)."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    template_id: int
    version_id: int
    version: int
    needs_clarification: bool
    clarification_question: str | None = None
    resolved_parameters: dict[str, Any] = Field(default_factory=dict)
    issues: list[ParameterExtractionIssueView] = Field(default_factory=list)
    sensitive_parameter_names: list[str] = Field(default_factory=list)


class LLMExtractedParameter(BaseModel):
    """One LLM-extracted name/value pair (untrusted until validated)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: Any


class LLMParameterExtraction(BaseModel):
    """Strict structured extraction output from the LLM."""

    model_config = ConfigDict(extra="forbid")

    values: list[LLMExtractedParameter] = Field(default_factory=list)
    unresolved_parameter_names: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_name_sets(self) -> LLMParameterExtraction:
        value_names = [item.name for item in self.values]
        if len(value_names) != len(set(value_names)):
            raise ValueError("duplicate parameter names in values")
        unresolved = list(self.unresolved_parameter_names)
        if len(unresolved) != len(set(unresolved)):
            raise ValueError("duplicate unresolved_parameter_names")
        overlap = set(value_names) & set(unresolved)
        if overlap:
            raise ValueError("values and unresolved_parameter_names must not overlap")
        for item in self.values:
            _assert_allowed_value_shape(item.value)
        return self


def _assert_allowed_value_shape(value: Any) -> None:
    if value is None:
        raise ValueError("extracted value must not be null")
    if isinstance(value, bool):
        return
    if isinstance(value, (str, int, float)):
        return
    if isinstance(value, list):
        if all(isinstance(item, str) for item in value):
            return
        if all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return
        raise ValueError("list values must be list[str] or list[int]")
    raise ValueError("extracted value must be a JSON scalar or list of scalars")
