"""Query Template registry repository."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.query_template import QueryTemplate, QueryTemplateVersion


class QueryTemplateRepository:
    """Persistence for QueryTemplate + QueryTemplateVersion rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, template_id: int) -> QueryTemplate | None:
        stmt = (
            select(QueryTemplate)
            .where(QueryTemplate.id == template_id)
            .options(selectinload(QueryTemplate.versions))
        )
        return self._session.scalars(stmt).first()

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

    def delete_template(self, template: QueryTemplate) -> None:
        # Clear circular current_version_id before cascading version deletes.
        template.current_version_id = None
        self._session.flush()
        self._session.delete(template)
        self._session.flush()
