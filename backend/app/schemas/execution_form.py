"""Schemas for Query Execution form metadata (QUERY_OPERATE projection)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_SOURCE_NAME_LENGTH = 255

ExecutionFormBlockerCode = Literal[
    "DEMIS_ADAPTER_UNAVAILABLE",
    "CONNECTION_PROFILE_INCOMPLETE",
]


class ExecutionFormParameter(BaseModel):
    """Safe parameter definition for operator form rendering."""

    model_config = ConfigDict(extra="forbid")

    name: str
    label: str | None = None
    description: str | None = None
    type: str
    required: bool = True
    default: Any | None = None
    allowed_values: list[Any] | None = None
    pattern: str | None = None
    min: int | float | None = None
    max: int | float | None = None
    min_items: int | None = None
    max_items: int | None = None
    sensitive: bool = False


class ExecutionFormTemplate(BaseModel):
    """Narrow template projection for Query Assistant forms."""

    model_config = ConfigDict(extra="forbid")

    template_id: int
    version_id: int
    version: int
    stable_key: str
    name: str
    description: str | None = None


class ExecutionFormEnvironment(BaseModel):
    """Enabled environment availability without Connection Profile secrets."""

    model_config = ConfigDict(extra="forbid")

    environment: str
    execution_available: bool
    execution_blockers: list[ExecutionFormBlockerCode] = Field(default_factory=list)


class ExecutionFormResponse(BaseModel):
    """QUERY_OPERATE-safe metadata for parameter form + environment selector."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    catalog_revision_id: int
    catalog_fingerprint: str
    template: ExecutionFormTemplate
    parameters: list[ExecutionFormParameter]
    environments: list[ExecutionFormEnvironment]
