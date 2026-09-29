"""Execution preview service (eligibility only; no DEMIS execution)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.schemas.execution_preview import (
    ExecutionPreviewRequest,
    ExecutionPreviewResponse,
)
from app.services.execution_eligibility import evaluate_execution_eligibility


def preview_query_execution(
    session: Session, request: ExecutionPreviewRequest
) -> ExecutionPreviewResponse:
    """Build a deterministic execution preview for operator confirmation.

    Does not connect to DEMIS, resolve credentials, execute SQL, call LLM,
    or write audit events.
    """
    result = evaluate_execution_eligibility(
        session,
        source_name=request.source_name,
        environment=request.environment,
        template_id=request.template_id,
        version_id=request.version_id,
        parameters=request.parameters,
    )
    return ExecutionPreviewResponse(
        source_name=result.source_name,
        environment=result.environment,
        catalog_revision_id=result.catalog_revision_id,
        catalog_fingerprint=result.catalog_fingerprint,
        template_id=result.template.id,
        version_id=result.version.id,
        version=result.version.version,
        connection_profile_id=result.connection_profile.id,
        resolved_parameters=result.resolved_parameters,
        sensitive_parameter_names=result.sensitive_parameter_names,
        row_limit=result.row_limit,
        timeout_seconds=result.timeout_seconds,
        execution_available=result.execution_available,
        execution_blockers=list(result.execution_blockers),
    )
