"""Pydantic contracts for Deterministic Query Compiler results (Phase 29-C)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.query_compiler import COMPILER_VERSION, CompilerIssueCode, CompilerStatus
from app.schemas.sql_safety import SqlSafetyReport

CompilerStatusLiteral = Literal["VALID", "INVALID", "NOT_CONFIGURED", "STALE"]


class CompilerIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: CompilerIssueCode | str
    message: str
    field_key: str | None = None
    relationship_key: str | None = None


class CompiledQueryResult(BaseModel):
    """Preview-only compiler output — not approved/executable authority.

    Callers must not treat this (or a caller-supplied ValidatedLogicalPlan) as
    a bypass of server-side validation. No credentials, patient data, execution
    tokens, or DB access are produced.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    preview_only: Literal[True] = True
    validation_only: Literal[True] = True
    approved: Literal[False] = False
    executable: Literal[False] = False
    status: CompilerStatus | CompilerStatusLiteral
    compiler_version: str = COMPILER_VERSION
    source_name: str
    catalog_revision_id: int | None = None
    schema_fingerprint: str | None = None
    mapping_version: str | None = None
    resource_key: str | None = None
    sql_text: str | None = None
    # Immutable bind map; JSON object on dump. Values never appear in sql_text.
    bind_parameters: dict[str, Any] = Field(default_factory=dict)
    sql_safety: SqlSafetyReport | None = None
    issues: tuple[CompilerIssue, ...] = ()


__all__ = [
    "CompiledQueryResult",
    "CompilerIssue",
]
