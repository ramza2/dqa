"""Query execution orchestration (eligibility + adapter + durable audit)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.demis.credentials import CredentialResolver
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.demis.factory import create_readonly_demis_adapter
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.adapters.demis.protocol import ReadOnlyDemisAdapter
from app.adapters.demis.types import ReadonlyQueryRequest
from app.adapters.execution.errors import (
    ExecutionError,
    ExecutionErrorCode,
    ExecutionPreviewError,
)
from app.auth.models import AuthenticatedActor
from app.models.connection_profile import ConnectionProfile
from app.schemas.audit import QueryAuditEventCreate, QueryAuditEventView, new_audit_id
from app.schemas.query_execution import QueryExecutionRequest, QueryExecutionResponse
from app.services.execution_eligibility import (
    ExecutionEligibilityResult,
    evaluate_execution_eligibility,
)
from app.services.query_audit import record_query_audit_event_durable

DurableAuditWriter = Callable[[QueryAuditEventCreate], QueryAuditEventView]
EligibilityFn = Callable[..., ExecutionEligibilityResult]
CredentialResolverFactory = Callable[[], CredentialResolver]
AdapterFactory = Callable[..., ReadOnlyDemisAdapter]


def execute_query(
    session: Session,
    request: QueryExecutionRequest,
    *,
    actor: AuthenticatedActor,
    audit_writer: DurableAuditWriter | None = None,
    eligibility_fn: EligibilityFn | None = None,
    credential_resolver_factory: CredentialResolverFactory | None = None,
    adapter_factory: AdapterFactory | None = None,
) -> QueryExecutionResponse:
    """Execute an approved Query Template through the read-only DEMIS adapter.

    Re-runs eligibility independently of any prior preview. Uses a durable audit
    writer so request-scoped rollback cannot erase the audit lifecycle.
    """
    from app.adapters.demis.credential_factory import create_credential_resolver

    writer = audit_writer or record_query_audit_event_durable
    run_eligibility = eligibility_fn or evaluate_execution_eligibility
    resolver_factory = credential_resolver_factory or create_credential_resolver
    build_adapter = adapter_factory or create_readonly_demis_adapter

    audit_id = new_audit_id()
    request_param_names = _request_parameter_names(request.parameters)

    _write_audit(
        writer,
        QueryAuditEventCreate(
            audit_id=audit_id,
            event_type="QUERY_REQUEST",
            status="STARTED",
            actor_id=actor.actor_id,
            source_name=request.source_name,
            template_id=request.template_id,
            template_version_id=request.version_id,
            parameter_names=request_param_names,
            sensitive_parameter_names=[],
        ),
        required=True,
    )

    try:
        eligibility = run_eligibility(
            session,
            source_name=request.source_name,
            environment=request.environment,
            template_id=request.template_id,
            version_id=request.version_id,
            parameters=request.parameters,
        )
    except ExecutionPreviewError as exc:
        _write_audit(
            writer,
            QueryAuditEventCreate(
                audit_id=audit_id,
                event_type="QUERY_REQUEST",
                status="DENIED",
                actor_id=actor.actor_id,
                source_name=request.source_name,
                template_id=request.template_id,
                template_version_id=request.version_id,
                parameter_names=request_param_names,
                sensitive_parameter_names=[],
                failure_category=exc.code,
            ),
            required=True,
        )
        raise

    if not eligibility.execution_available:
        param_names, sensitive_names = _eligibility_audit_names(eligibility)
        _write_audit(
            writer,
            QueryAuditEventCreate(
                audit_id=audit_id,
                event_type="QUERY_REQUEST",
                status="DENIED",
                actor_id=actor.actor_id,
                source_name=eligibility.source_name,
                catalog_revision_id=eligibility.catalog_revision_id,
                catalog_fingerprint=eligibility.catalog_fingerprint,
                template_id=eligibility.template.id,
                template_version_id=eligibility.version.id,
                connection_profile_id=eligibility.connection_profile.id,
                parameter_names=param_names,
                sensitive_parameter_names=sensitive_names,
                failure_category=ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE,
            ),
            required=True,
        )
        raise ExecutionError(
            ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE,
            "no concrete DEMIS read-only adapter is available for execution",
        )

    param_names, sensitive_names = _eligibility_audit_names(eligibility)
    _write_audit(
        writer,
        QueryAuditEventCreate(
            audit_id=audit_id,
            event_type="QUERY_REQUEST",
            status="SUCCEEDED",
            actor_id=actor.actor_id,
            source_name=eligibility.source_name,
            catalog_revision_id=eligibility.catalog_revision_id,
            catalog_fingerprint=eligibility.catalog_fingerprint,
            template_id=eligibility.template.id,
            template_version_id=eligibility.version.id,
            connection_profile_id=eligibility.connection_profile.id,
            parameter_names=param_names,
            sensitive_parameter_names=sensitive_names,
        ),
        required=True,
    )

    snapshot = _profile_snapshot(eligibility.connection_profile)
    try:
        resolver = resolver_factory()
        adapter = build_adapter(snapshot, credential_resolver=resolver)
    except DemisAdapterError as exc:
        _write_audit(
            writer,
            QueryAuditEventCreate(
                audit_id=audit_id,
                event_type="QUERY_EXECUTION",
                status="FAILED",
                actor_id=actor.actor_id,
                source_name=eligibility.source_name,
                catalog_revision_id=eligibility.catalog_revision_id,
                catalog_fingerprint=eligibility.catalog_fingerprint,
                template_id=eligibility.template.id,
                template_version_id=eligibility.version.id,
                connection_profile_id=eligibility.connection_profile.id,
                parameter_names=param_names,
                sensitive_parameter_names=sensitive_names,
                failure_category=exc.failure_category,
            ),
            required=True,
        )
        raise
    except ExecutionError:
        raise
    except Exception:
        _write_audit(
            writer,
            QueryAuditEventCreate(
                audit_id=audit_id,
                event_type="QUERY_EXECUTION",
                status="FAILED",
                actor_id=actor.actor_id,
                source_name=eligibility.source_name,
                catalog_revision_id=eligibility.catalog_revision_id,
                catalog_fingerprint=eligibility.catalog_fingerprint,
                template_id=eligibility.template.id,
                template_version_id=eligibility.version.id,
                connection_profile_id=eligibility.connection_profile.id,
                parameter_names=param_names,
                sensitive_parameter_names=sensitive_names,
                failure_category=DemisAdapterErrorCode.EXECUTION_FAILED,
            ),
            required=True,
        )
        raise DemisAdapterError(
            DemisAdapterErrorCode.EXECUTION_FAILED,
            "read-only query execution failed",
        ) from None

    query_request = ReadonlyQueryRequest(
        sql_text=eligibility.version.sql_text,
        parameters=dict(eligibility.resolved_parameters),
        timeout_seconds=eligibility.timeout_seconds,
        row_limit=eligibility.row_limit,
    )

    _write_audit(
        writer,
        QueryAuditEventCreate(
            audit_id=audit_id,
            event_type="QUERY_EXECUTION",
            status="STARTED",
            actor_id=actor.actor_id,
            source_name=eligibility.source_name,
            catalog_revision_id=eligibility.catalog_revision_id,
            catalog_fingerprint=eligibility.catalog_fingerprint,
            template_id=eligibility.template.id,
            template_version_id=eligibility.version.id,
            connection_profile_id=eligibility.connection_profile.id,
            parameter_names=param_names,
            sensitive_parameter_names=sensitive_names,
        ),
        required=True,
    )

    try:
        result = adapter.execute_readonly(query_request)
    except DemisAdapterError as exc:
        _write_audit(
            writer,
            QueryAuditEventCreate(
                audit_id=audit_id,
                event_type="QUERY_EXECUTION",
                status="FAILED",
                actor_id=actor.actor_id,
                source_name=eligibility.source_name,
                catalog_revision_id=eligibility.catalog_revision_id,
                catalog_fingerprint=eligibility.catalog_fingerprint,
                template_id=eligibility.template.id,
                template_version_id=eligibility.version.id,
                connection_profile_id=eligibility.connection_profile.id,
                parameter_names=param_names,
                sensitive_parameter_names=sensitive_names,
                failure_category=exc.failure_category,
            ),
            required=True,
        )
        raise
    except Exception:
        _write_audit(
            writer,
            QueryAuditEventCreate(
                audit_id=audit_id,
                event_type="QUERY_EXECUTION",
                status="FAILED",
                actor_id=actor.actor_id,
                source_name=eligibility.source_name,
                catalog_revision_id=eligibility.catalog_revision_id,
                catalog_fingerprint=eligibility.catalog_fingerprint,
                template_id=eligibility.template.id,
                template_version_id=eligibility.version.id,
                connection_profile_id=eligibility.connection_profile.id,
                parameter_names=param_names,
                sensitive_parameter_names=sensitive_names,
                failure_category=DemisAdapterErrorCode.EXECUTION_FAILED,
            ),
            required=True,
        )
        raise DemisAdapterError(
            DemisAdapterErrorCode.EXECUTION_FAILED,
            "read-only query execution failed",
        ) from None

    _write_audit(
        writer,
        QueryAuditEventCreate(
            audit_id=audit_id,
            event_type="QUERY_EXECUTION",
            status="SUCCEEDED",
            actor_id=actor.actor_id,
            source_name=eligibility.source_name,
            catalog_revision_id=eligibility.catalog_revision_id,
            catalog_fingerprint=eligibility.catalog_fingerprint,
            template_id=eligibility.template.id,
            template_version_id=eligibility.version.id,
            connection_profile_id=eligibility.connection_profile.id,
            parameter_names=param_names,
            sensitive_parameter_names=sensitive_names,
            elapsed_ms=result.elapsed_ms,
            row_count=result.row_count,
            result_truncated=result.truncated,
        ),
        required=True,
    )

    return QueryExecutionResponse(
        audit_id=audit_id,
        source_name=eligibility.source_name,
        environment=eligibility.environment,
        catalog_revision_id=eligibility.catalog_revision_id,
        catalog_fingerprint=eligibility.catalog_fingerprint,
        template_id=eligibility.template.id,
        version_id=eligibility.version.id,
        version=eligibility.version.version,
        connection_profile_id=eligibility.connection_profile.id,
        columns=list(result.columns),
        rows=list(result.rows),
        row_count=result.row_count,
        truncated=result.truncated,
        elapsed_ms=result.elapsed_ms,
    )


def _write_audit(
    writer: DurableAuditWriter,
    payload: QueryAuditEventCreate,
    *,
    required: bool,
) -> QueryAuditEventView | None:
    try:
        return writer(payload)
    except ExecutionError:
        raise
    except Exception:
        if required:
            raise ExecutionError(
                ExecutionErrorCode.AUDIT_UNAVAILABLE,
                "query audit could not be persisted",
            ) from None
        return None


def _request_parameter_names(parameters: dict[str, Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for raw in parameters:
        if not isinstance(raw, str):
            continue
        name = raw.strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _eligibility_audit_names(
    eligibility: ExecutionEligibilityResult,
) -> tuple[list[str], list[str]]:
    param_names = [param.name for param in eligibility.parameters]
    sensitive = [
        name
        for name in eligibility.sensitive_parameter_names
        if name in set(param_names)
    ]
    return param_names, sensitive


def _profile_snapshot(profile: ConnectionProfile) -> ConnectionProfileSnapshot:
    return ConnectionProfileSnapshot.model_validate(
        {
            "profile_id": profile.id,
            "name": profile.name,
            "source_name": profile.source_name,
            "environment": profile.environment,
            "enabled": profile.enabled,
            "dbms_type": profile.dbms_type,
            "host": profile.host,
            "port": profile.port,
            "database_name": profile.database_name,
            "username": profile.username,
            "credential_secret_ref": profile.credential_secret_ref,
        }
    )
