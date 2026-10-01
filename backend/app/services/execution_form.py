"""Query Execution form metadata (parameter + environment projection)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import CatalogActivationError
from app.adapters.demis.factory import (
    is_concrete_demis_adapter_available,
    required_adapter_config_present,
)
from app.adapters.demis.types import MAX_SQL_TEXT_LENGTH
from app.adapters.execution.errors import (
    ExecutionPreviewError,
    ExecutionPreviewErrorCode,
)
from app.models.connection_profile import ConnectionProfile
from app.repositories.connection_profile import ConnectionProfileRepository
from app.schemas.execution_form import (
    ExecutionFormBlockerCode,
    ExecutionFormEnvironment,
    ExecutionFormParameter,
    ExecutionFormResponse,
    ExecutionFormTemplate,
)
from app.schemas.query_template import QueryTemplateParameter
from app.services.catalog_active import get_active_catalog
from app.services.execution_eligibility import require_eligible_executable_template
from app.services.sql_safety import validate_sql_safety


def get_execution_form_metadata(
    session: Session,
    *,
    source_name: str,
    template_id: int,
    version_id: int,
) -> ExecutionFormResponse:
    """Return QUERY_OPERATE-safe form metadata for Query Assistant.

    Does not require parameter values, resolve credentials, connect to DEMIS,
    execute SQL, call LLM, or write audit events.
    """
    cleaned_source = source_name.strip()
    if not cleaned_source:
        raise ExecutionPreviewError(
            ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE,
            "source_name must not be blank",
        )

    template, version = require_eligible_executable_template(
        session,
        source_name=cleaned_source,
        template_id=template_id,
        version_id=version_id,
    )

    try:
        active = get_active_catalog(session, cleaned_source)
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

    environments = _project_enabled_environments(session, cleaned_source)

    return ExecutionFormResponse(
        source_name=cleaned_source,
        catalog_revision_id=active.revision_id,
        catalog_fingerprint=active.schema_fingerprint,
        template=ExecutionFormTemplate(
            template_id=template.id,
            version_id=version.id,
            version=version.version,
            stable_key=template.stable_key,
            name=template.name,
            description=template.description,
        ),
        parameters=[_project_parameter(param) for param in parameter_schema],
        environments=environments,
    )


def _project_parameter(param: QueryTemplateParameter) -> ExecutionFormParameter:
    return ExecutionFormParameter(
        name=param.name,
        label=param.label,
        description=param.description,
        type=param.type,
        required=param.required,
        default=_json_safe_default(param.default),
        allowed_values=(
            [_json_safe_default(value) for value in param.allowed_values]
            if param.allowed_values is not None
            else None
        ),
        pattern=param.pattern,
        min=_json_safe_number(param.min),
        max=_json_safe_number(param.max),
        min_items=param.min_items,
        max_items=param.max_items,
        sensitive=param.sensitive,
    )


def _json_safe_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _json_safe_number(value: int | float | Decimal | None) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _project_enabled_environments(
    session: Session, source_name: str
) -> list[ExecutionFormEnvironment]:
    """Expose enabled profiles only; never include host/user/credential metadata.

    Policy for incomplete enabled profiles: include with
    ``execution_available=false`` and ``CONNECTION_PROFILE_INCOMPLETE``.
    Disabled profiles are omitted entirely.
    """
    profiles = ConnectionProfileRepository(session).list_profiles(
        source_name=source_name,
        limit=500,
        offset=0,
    )
    enabled = [profile for profile in profiles if profile.enabled]
    enabled.sort(key=lambda item: (item.environment, item.id))

    projected: list[ExecutionFormEnvironment] = []
    for profile in enabled:
        blockers = _environment_blockers(profile)
        projected.append(
            ExecutionFormEnvironment(
                environment=profile.environment,
                execution_available=len(blockers) == 0,
                execution_blockers=blockers,
            )
        )
    return projected


def _environment_blockers(
    profile: ConnectionProfile,
) -> list[ExecutionFormBlockerCode]:
    if not required_adapter_config_present(
        dbms_type=profile.dbms_type,
        host=profile.host,
        port=profile.port,
        database_name=profile.database_name,
        username=profile.username,
        credential_secret_ref=profile.credential_secret_ref,
    ):
        return ["CONNECTION_PROFILE_INCOMPLETE"]
    if not is_concrete_demis_adapter_available(profile.dbms_type):
        return ["DEMIS_ADAPTER_UNAVAILABLE"]
    return []
