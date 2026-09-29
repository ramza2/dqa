"""Schemas for Query Execution execute API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.execution_preview import ExecutionPreviewRequest

# Execute uses the same caller-controlled fields as preview.
QueryExecutionRequest = ExecutionPreviewRequest


class QueryExecutionResponse(BaseModel):
    """Normalized read-only execution result for operator review.

    ``rows`` may contain sensitive medical data. Callers must not log, persist,
    or send rows to an LLM. Representation omits row payloads.
    """

    model_config = ConfigDict(extra="forbid")

    audit_id: str
    source_name: str
    environment: str
    catalog_revision_id: int
    catalog_fingerprint: str
    template_id: int
    version_id: int
    version: int
    connection_profile_id: int
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    truncated: bool
    elapsed_ms: int = Field(ge=0)

    def __repr__(self) -> str:
        return (
            "QueryExecutionResponse("
            f"audit_id={self.audit_id!r}, "
            f"template_id={self.template_id}, "
            f"version_id={self.version_id}, "
            f"column_count={len(self.columns)}, "
            f"row_count={self.row_count}, "
            f"truncated={self.truncated}, "
            f"elapsed_ms={self.elapsed_ms})"
        )
