"""Query Audit foundation service (append-only writer + read)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from app.adapters.audit.errors import AuditError, AuditErrorCode
from app.models.query_audit import QueryAuditEvent
from app.repositories.query_audit import QueryAuditEventRepository
from app.schemas.audit import (
    ALLOWED_EVENT_TYPES,
    ALLOWED_STATUSES,
    QueryAuditEventCreate,
    QueryAuditEventListResponse,
    QueryAuditEventView,
    new_audit_id,
)

PARAMETER_LOGGING_POLICY = "NAMES_ONLY"


def record_query_audit_event(
    session: Session,
    payload: QueryAuditEventCreate,
) -> QueryAuditEventView:
    """Append one immutable audit event.

    Callers must use ``QueryAuditEventCreate`` which forbids parameter values,
    SQL, request text, result rows, and credentials.
    """
    if payload.event_type not in ALLOWED_EVENT_TYPES:
        raise AuditError(
            AuditErrorCode.INVALID_REQUEST,
            "unsupported audit event_type",
        )
    if payload.status not in ALLOWED_STATUSES:
        raise AuditError(
            AuditErrorCode.INVALID_REQUEST,
            "unsupported audit status",
        )

    # sensitive names must be a subset of declared parameter names
    param_set = set(payload.parameter_names)
    for name in payload.sensitive_parameter_names:
        if name not in param_set:
            raise AuditError(
                AuditErrorCode.INVALID_REQUEST,
                "sensitive_parameter_names must be subset of parameter_names",
            )

    audit_id = payload.audit_id or new_audit_id()
    event = QueryAuditEvent(
        audit_id=audit_id,
        event_type=payload.event_type,
        status=payload.status,
        actor_id=payload.actor_id,
        source_name=payload.source_name,
        catalog_revision_id=payload.catalog_revision_id,
        catalog_fingerprint=payload.catalog_fingerprint,
        template_id=payload.template_id,
        template_version_id=payload.template_version_id,
        connection_profile_id=payload.connection_profile_id,
        parameter_names=list(payload.parameter_names),
        sensitive_parameter_names=list(payload.sensitive_parameter_names),
        parameter_logging_policy=PARAMETER_LOGGING_POLICY,
        failure_category=payload.failure_category,
        elapsed_ms=payload.elapsed_ms,
        row_count=payload.row_count,
        result_truncated=payload.result_truncated,
        created_at=datetime.now(timezone.utc),
    )
    QueryAuditEventRepository(session).add(event)
    return _to_view(event)


def record_query_audit_event_durable(
    payload: QueryAuditEventCreate,
    *,
    session_factory: sessionmaker[Session] | None = None,
) -> QueryAuditEventView:
    """Append and commit one audit event on an independent short-lived session.

    Used by production query execution so request-scoped rollback cannot erase
    the audit lifecycle. Reuses ``record_query_audit_event`` validation.
    Never accepts parameter values, result rows, SQL, or secrets.
    """
    from app.adapters.db.session import get_session_factory

    factory = session_factory or get_session_factory()
    session = factory()
    try:
        view = record_query_audit_event(session, payload)
        session.commit()
        return view
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_query_audit_events(
    session: Session,
    *,
    audit_id: str | None = None,
    actor_id: str | None = None,
    source_name: str | None = None,
    template_id: int | None = None,
    event_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> QueryAuditEventListResponse:
    if event_type is not None and event_type not in ALLOWED_EVENT_TYPES:
        raise AuditError(
            AuditErrorCode.INVALID_REQUEST,
            "unsupported audit event_type filter",
        )
    if status is not None and status not in ALLOWED_STATUSES:
        raise AuditError(
            AuditErrorCode.INVALID_REQUEST,
            "unsupported audit status filter",
        )

    repo = QueryAuditEventRepository(session)
    items = repo.list_events(
        audit_id=audit_id,
        actor_id=actor_id,
        source_name=source_name,
        template_id=template_id,
        event_type=event_type,
        status=status,
        limit=limit,
        offset=offset,
    )
    total = repo.count_events(
        audit_id=audit_id,
        actor_id=actor_id,
        source_name=source_name,
        template_id=template_id,
        event_type=event_type,
        status=status,
    )
    return QueryAuditEventListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_to_view(item) for item in items],
    )


def get_query_audit_events_by_audit_id(
    session: Session, audit_id: str
) -> list[QueryAuditEventView]:
    """Return all append-only rows for one audit correlation id."""
    cleaned = audit_id.strip()
    if not cleaned:
        raise AuditError(AuditErrorCode.INVALID_REQUEST, "audit_id must not be blank")
    events = QueryAuditEventRepository(session).list_by_audit_id(cleaned)
    if not events:
        raise AuditError(AuditErrorCode.NOT_FOUND, "audit event not found")
    return [_to_view(item) for item in events]


def _to_view(event: QueryAuditEvent) -> QueryAuditEventView:
    return QueryAuditEventView(
        id=event.id,
        audit_id=event.audit_id,
        event_type=event.event_type,  # type: ignore[arg-type]
        status=event.status,  # type: ignore[arg-type]
        actor_id=event.actor_id,
        source_name=event.source_name,
        catalog_revision_id=event.catalog_revision_id,
        catalog_fingerprint=event.catalog_fingerprint,
        template_id=event.template_id,
        template_version_id=event.template_version_id,
        connection_profile_id=event.connection_profile_id,
        parameter_names=list(event.parameter_names or []),
        sensitive_parameter_names=list(event.sensitive_parameter_names or []),
        parameter_logging_policy=event.parameter_logging_policy,  # type: ignore[arg-type]
        failure_category=event.failure_category,
        elapsed_ms=event.elapsed_ms,
        row_count=event.row_count,
        result_truncated=event.result_truncated,
        created_at=event.created_at,
    )
