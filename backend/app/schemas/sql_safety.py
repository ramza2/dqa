"""SQL Safety Validator report schemas (no execution)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SqlSafetyIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class SqlSafetyReport(BaseModel):
    """Deterministic SQL safety validation outcome for one SQL text + parameter schema."""

    model_config = ConfigDict(extra="forbid")

    safe: bool
    statement_count: int = Field(ge=0)
    referenced_parameters: list[str]
    declared_parameters: list[str]
    issues: list[SqlSafetyIssue]


class QueryTemplateSqlSafetyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: int
    version_id: int
    version: int
    safe: bool
    statement_count: int
    referenced_parameters: list[str]
    declared_parameters: list[str]
    issues: list[SqlSafetyIssue]
