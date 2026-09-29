"""Deterministic execution eligibility gate (shared by preview and future execute).

Does not connect to DEMIS, resolve credentials, execute SQL, call LLM, or write audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import CatalogActivationError
from app.adapters.demis.factory import (
    is_concrete_demis_adapter_available,
    required_adapter_config_present,
)
from app.adapters.demis.types import (
    MAX_ROW_LIMIT,
    MAX_SQL_TEXT_LENGTH,
    MAX_TIMEOUT_SECONDS,
)
from app.adapters.execution.errors import (
    ExecutionPreviewError,
    ExecutionPreviewErrorCode,
)
from app.models.connection_profile import ConnectionProfile
from app.models.query_template import QueryTemplate, QueryTemplateVersion
from app.repositories.connection_profile import ConnectionProfileRepository
from app.repositories.query_template import QueryTemplateRepository
from app.schemas.query_template import QueryTemplateParameter
from app.services.catalog_active import get_active_catalog
from app.services.parameter_validation import validate_parameter_values
from app.services.query_template import APPROVAL_APPROVED
from app.services.sql_safety import validate_sql_safety

ExecutionBlocker = Literal["DEMIS_ADAPTER_UNAVAILABLE"]


@dataclass(frozen=True)
class ExecutionEligibilityResult:
    """Reusable outcome of the production execution eligibility gate."""

    source_name: str
    environment: str
    template: QueryTemplate
    version: QueryTemplateVersion
    catalog_revision_id: int
    catalog_fingerprint: str
    connection_profile: ConnectionProfile
    parameters: list[QueryTemplateParameter]
    resolved_parameters: dict[str, Any]
    sensitive_parameter_names: list[str]
    row_limit: int
    timeout_seconds: int
    execution_available: bool
    execution_blockers: list[ExecutionBlocker] = field(default_factory=list)


def evaluate_execution_eligibility(
    session: Session,
    *,
    source_name: str,
    environment: str,
    template_id: int,
    version_id: int,
    parameters: dict[str, Any],
) -> ExecutionEligibilityResult:
    """Independently re-check all deterministic gates for preview/execute.

    Never resolves credentials or calls ``ReadOnlyDemisAdapter.execute_readonly``.
    """
    template, version = _require_eligible_template(
        session,
        source_name=source_name,
        template_id=template_id,
        version_id=version_id,
    )

    try:
        active = get_active_catalog(session, source_name)
    except CatalogActivationError:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.ACTIVE_CATALOG_NOT_FOUND,
            "active catalog revision not found for source",
        ) from None

    if version.catalog_revision_id != active.revision_id:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.CATALOG_MISMATCH,
            "query template catalog revision does not match the active catalog",
        )
    if version.catalog_fingerprint_constraint != active.schema_fingerprint:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.CATALOG_MISMATCH,
            "query template catalog fingerprint does not match the active catalog",
        )

    if len(version.sql_text) > MAX_SQL_TEXT_LENGTH:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE,
            "query template sql_text exceeds allowed production limits",
        )

    report = validate_sql_safety(version.sql_text, version.parameter_schema)
    if not report.safe:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.SQL_UNSAFE,
            "query template SQL does not pass safety validation",
        )

    try:
        parameter_schema = [
            QueryTemplateParameter.model_validate(item)
            for item in (version.parameter_schema or [])
        ]
    except Exception:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.PARAMETER_SCHEMA_INVALID,
            "template parameter schema is invalid",
        ) from None

    _reject_undeclared_parameters(parameter_schema, parameters)

    validation = validate_parameter_values(parameter_schema, parameters, unresolved_names=[])
    if validation.needs_clarification:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.PARAMETER_INVALID,
            "request parameters failed deterministic validation",
        )

    profile = _require_eligible_connection_profile(
        session, source_name=source_name, environment=environment
    )

    row_limit, timeout_seconds = _validate_execution_limits(version)

    blockers: list[ExecutionBlocker] = []
    if not is_concrete_demis_adapter_available(profile.dbms_type):
        blockers.append("DEMIS_ADAPTER_UNAVAILABLE")

    sensitive_names = sorted(param.name for param in parameter_schema if param.sensitive)

    return ExecutionEligibilityResult(
        source_name=source_name,
        environment=environment,
        template=template,
        version=version,
        catalog_revision_id=active.revision_id,
        catalog_fingerprint=active.schema_fingerprint,
        connection_profile=profile,
        parameters=parameter_schema,
        resolved_parameters=dict(validation.resolved_parameters),
        sensitive_parameter_names=sensitive_names,
        row_limit=row_limit,
        timeout_seconds=timeout_seconds,
        execution_available=len(blockers) == 0,
        execution_blockers=blockers,
    )


def require_eligible_executable_template(
    session: Session,
    *,
    source_name: str,
    template_id: int,
    version_id: int,
) -> tuple[QueryTemplate, QueryTemplateVersion]:
    """Public wrapper: approved + enabled + current version for the source."""
    return _require_eligible_template(
        session,
        source_name=source_name,
        template_id=template_id,
        version_id=version_id,
    )


def _require_eligible_template(
    session: Session,
    *,
    source_name: str,
    template_id: int,
    version_id: int,
) -> tuple[QueryTemplate, QueryTemplateVersion]:
    repo = QueryTemplateRepository(session)
    template = repo.get_by_id(template_id)
    if template is None:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.TEMPLATE_NOT_FOUND,
            "query template not found",
        )
    if template.source_name != source_name:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE,
            "query template source does not match the request",
        )
    if template.current_version_id != version_id:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION,
            "requested version is not the current template version",
        )

    version = next((item for item in template.versions if item.id == version_id), None)
    if version is None:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION,
            "requested version is not the current template version",
        )

    if not template.enabled or version.approval_status != APPROVAL_APPROVED:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE,
            "query template is not approved and enabled",
        )
    return template, version


def _reject_undeclared_parameters(
    parameter_schema: list[QueryTemplateParameter],
    parameters: dict[str, Any],
) -> None:
    declared = {param.name for param in parameter_schema}
    undeclared = [name for name in parameters if name not in declared]
    if undeclared:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.PARAMETER_UNDECLARED,
            "request contains undeclared parameter names",
        )


def _require_eligible_connection_profile(
    session: Session,
    *,
    source_name: str,
    environment: str,
) -> ConnectionProfile:
    profile = ConnectionProfileRepository(session).get_by_source_and_environment(
        source_name, environment
    )
    if profile is None:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND,
            "connection profile not found for source and environment",
        )
    if profile.source_name != source_name or profile.environment != environment:
        # Defensive: repository already filters; keep binding explicit.
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND,
            "connection profile not found for source and environment",
        )
    if not profile.enabled:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.CONNECTION_PROFILE_DISABLED,
            "connection profile is disabled",
        )
    if not required_adapter_config_present(
        dbms_type=profile.dbms_type,
        host=profile.host,
        port=profile.port,
        database_name=profile.database_name,
        username=profile.username,
        credential_secret_ref=profile.credential_secret_ref,
    ):
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.CONNECTION_PROFILE_INCOMPLETE,
            "connection profile adapter configuration metadata is incomplete",
        )
    return profile


def _validate_execution_limits(version: QueryTemplateVersion) -> tuple[int, int]:
    row_limit = version.row_limit
    timeout_seconds = version.timeout_seconds
    if row_limit <= 0 or row_limit > MAX_ROW_LIMIT:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE,
            "query template row_limit exceeds allowed production limits",
        )
    if timeout_seconds <= 0 or timeout_seconds > MAX_TIMEOUT_SECONDS:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE,
            "query template timeout_seconds exceeds allowed production limits",
        )
    return row_limit, timeout_seconds
