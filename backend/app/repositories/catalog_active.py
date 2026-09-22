"""Active Catalog pointer and activation-event repository."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.catalog_active import CatalogActivationEvent, CatalogActiveRevision


class CatalogActiveRepository:
    """Persistence for active pointers (upsert) and append-only activation events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active_by_source_name(
        self,
        source_name: str,
        *,
        for_update: bool = False,
    ) -> CatalogActiveRevision | None:
        stmt = select(CatalogActiveRevision).where(
            CatalogActiveRevision.source_name == source_name
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self._session.scalars(stmt).first()

    def list_active(self) -> list[CatalogActiveRevision]:
        stmt = select(CatalogActiveRevision).order_by(
            CatalogActiveRevision.source_name.asc(),
            CatalogActiveRevision.id.asc(),
        )
        return list(self._session.scalars(stmt).all())

    def add_active(self, pointer: CatalogActiveRevision) -> CatalogActiveRevision:
        self._session.add(pointer)
        self._session.flush()
        self._session.refresh(pointer)
        return pointer

    def add_event(self, event: CatalogActivationEvent) -> CatalogActivationEvent:
        """Append an activation event. Callers must not update/delete events via API."""
        self._session.add(event)
        self._session.flush()
        self._session.refresh(event)
        return event

    def list_events(
        self,
        *,
        source_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CatalogActivationEvent]:
        stmt: Select[tuple[CatalogActivationEvent]] = select(CatalogActivationEvent)
        if source_name is not None:
            stmt = stmt.where(CatalogActivationEvent.source_name == source_name)
        stmt = (
            stmt.order_by(
                CatalogActivationEvent.activated_at.desc(),
                CatalogActivationEvent.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt).all())

    def count_events(self, *, source_name: str | None = None) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(CatalogActivationEvent)
        if source_name is not None:
            stmt = stmt.where(CatalogActivationEvent.source_name == source_name)
        return int(self._session.scalar(stmt) or 0)
