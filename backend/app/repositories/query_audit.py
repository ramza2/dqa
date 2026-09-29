"""Query Audit Event repository (append-only)."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.query_audit import QueryAuditEvent


class QueryAuditEventRepository:
    """Persistence for append-only query audit events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: QueryAuditEvent) -> QueryAuditEvent:
        self._session.add(event)
        self._session.flush()
        return event

    def get_by_id(self, event_id: int) -> QueryAuditEvent | None:
        stmt = select(QueryAuditEvent).where(QueryAuditEvent.id == event_id)
        return self._session.scalars(stmt).first()

    def list_by_audit_id(self, audit_id: str) -> list[QueryAuditEvent]:
        stmt = (
            select(QueryAuditEvent)
            .where(QueryAuditEvent.audit_id == audit_id)
            .order_by(QueryAuditEvent.created_at.desc(), QueryAuditEvent.id.desc())
        )
        return list(self._session.scalars(stmt).all())

    def list_events(
        self,
        *,
        audit_id: str | None = None,
        actor_id: str | None = None,
        source_name: str | None = None,
        template_id: int | None = None,
        event_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[QueryAuditEvent]:
        stmt = self._filtered_stmt(
            audit_id=audit_id,
            actor_id=actor_id,
            source_name=source_name,
            template_id=template_id,
            event_type=event_type,
            status=status,
        )
        stmt = (
            stmt.order_by(QueryAuditEvent.created_at.desc(), QueryAuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt).all())

    def count_events(
        self,
        *,
        audit_id: str | None = None,
        actor_id: str | None = None,
        source_name: str | None = None,
        template_id: int | None = None,
        event_type: str | None = None,
        status: str | None = None,
    ) -> int:
        base = self._filtered_stmt(
            audit_id=audit_id,
            actor_id=actor_id,
            source_name=source_name,
            template_id=template_id,
            event_type=event_type,
            status=status,
        )
        stmt = select(func.count()).select_from(base.subquery())
        return int(self._session.scalar(stmt) or 0)

    def _filtered_stmt(
        self,
        *,
        audit_id: str | None,
        actor_id: str | None,
        source_name: str | None,
        template_id: int | None,
        event_type: str | None,
        status: str | None,
    ) -> Select[tuple[QueryAuditEvent]]:
        stmt: Select[tuple[QueryAuditEvent]] = select(QueryAuditEvent)
        if audit_id is not None:
            stmt = stmt.where(QueryAuditEvent.audit_id == audit_id)
        if actor_id is not None:
            stmt = stmt.where(QueryAuditEvent.actor_id == actor_id)
        if source_name is not None:
            stmt = stmt.where(QueryAuditEvent.source_name == source_name)
        if template_id is not None:
            stmt = stmt.where(QueryAuditEvent.template_id == template_id)
        if event_type is not None:
            stmt = stmt.where(QueryAuditEvent.event_type == event_type)
        if status is not None:
            stmt = stmt.where(QueryAuditEvent.status == status)
        return stmt
