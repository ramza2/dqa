"""Query Template registry repository."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.query_template import (
    QueryTemplate,
    QueryTemplateReviewEvent,
    QueryTemplateVersion,
)


class QueryTemplateRepository:
    """Persistence for QueryTemplate + QueryTemplateVersion + review events."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, template_id: int) -> QueryTemplate | None:
        stmt = (
            select(QueryTemplate)
            .where(QueryTemplate.id == template_id)
            .options(selectinload(QueryTemplate.versions))
        )
        return self._session.scalars(stmt).first()

    def get_by_id_for_update(self, template_id: int) -> QueryTemplate | None:
        """Lock the stable template row for lifecycle transitions."""
        stmt = (
            select(QueryTemplate)
            .where(QueryTemplate.id == template_id)
            .with_for_update()
        )
        template = self._session.scalars(stmt).first()
        if template is None:
            return None
        # Reload versions after lock without holding a second lock race window.
        self._session.refresh(template, attribute_names=["versions"])
        return template

    def get_by_source_and_stable_key(
        self, source_name: str, stable_key: str
    ) -> QueryTemplate | None:
        stmt = select(QueryTemplate).where(
            QueryTemplate.source_name == source_name,
            QueryTemplate.stable_key == stable_key,
        )
        return self._session.scalars(stmt).first()

    def list_templates(
        self,
        *,
        source_name: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[QueryTemplate]:
        stmt: Select[tuple[QueryTemplate]] = select(QueryTemplate).options(
            selectinload(QueryTemplate.versions)
        )
        if source_name is not None:
            stmt = stmt.where(QueryTemplate.source_name == source_name)
        stmt = (
            stmt.order_by(QueryTemplate.updated_at.desc(), QueryTemplate.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt).all())

    def count_templates(self, *, source_name: str | None = None) -> int:
        stmt = select(func.count()).select_from(QueryTemplate)
        if source_name is not None:
            stmt = stmt.where(QueryTemplate.source_name == source_name)
        return int(self._session.scalar(stmt) or 0)

    def list_versions(self, template_id: int) -> list[QueryTemplateVersion]:
        stmt = (
            select(QueryTemplateVersion)
            .where(QueryTemplateVersion.template_id == template_id)
            .order_by(QueryTemplateVersion.version.asc(), QueryTemplateVersion.id.asc())
        )
        return list(self._session.scalars(stmt).all())

    def max_version_number(self, template_id: int) -> int:
        stmt = select(func.max(QueryTemplateVersion.version)).where(
            QueryTemplateVersion.template_id == template_id
        )
        return int(self._session.scalar(stmt) or 0)

    def add_template(self, template: QueryTemplate) -> QueryTemplate:
        self._session.add(template)
        self._session.flush()
        self._session.refresh(template)
        return template

    def add_version(self, version: QueryTemplateVersion) -> QueryTemplateVersion:
        self._session.add(version)
        self._session.flush()
        self._session.refresh(version)
        return version

    def add_review_event(self, event: QueryTemplateReviewEvent) -> QueryTemplateReviewEvent:
        """Append-only insert. Callers must not update/delete events."""
        self._session.add(event)
        self._session.flush()
        self._session.refresh(event)
        return event

    def list_review_events(self, template_id: int) -> list[QueryTemplateReviewEvent]:
        stmt = (
            select(QueryTemplateReviewEvent)
            .where(QueryTemplateReviewEvent.template_id == template_id)
            .order_by(
                QueryTemplateReviewEvent.created_at.asc(),
                QueryTemplateReviewEvent.id.asc(),
            )
        )
        return list(self._session.scalars(stmt).all())

    def delete_template(self, template: QueryTemplate) -> None:
        # Clear circular current_version_id before cascading version deletes.
        template.current_version_id = None
        self._session.flush()
        self._session.delete(template)
        self._session.flush()
