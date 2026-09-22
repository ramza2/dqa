"""Catalog import revision repository (create + read only)."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.models.catalog_import import CatalogImportRevision


class CatalogImportRepository:
    """Persistence access for immutable CatalogImportRevision rows."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, revision_id: int) -> CatalogImportRevision | None:
        return self._session.get(CatalogImportRevision, revision_id)

    def get_by_archive_sha256(self, archive_sha256: str) -> CatalogImportRevision | None:
        stmt = select(CatalogImportRevision).where(
            CatalogImportRevision.archive_sha256 == archive_sha256
        )
        return self._session.scalars(stmt).first()

    def list_revisions(
        self,
        *,
        source_name: str | None = None,
        package_readiness: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CatalogImportRevision]:
        stmt: Select[tuple[CatalogImportRevision]] = select(CatalogImportRevision)
        if source_name is not None:
            stmt = stmt.where(CatalogImportRevision.source_name == source_name)
        if package_readiness is not None:
            stmt = stmt.where(CatalogImportRevision.package_readiness == package_readiness)
        stmt = (
            stmt.order_by(CatalogImportRevision.imported_at.desc(), CatalogImportRevision.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self._session.scalars(stmt).all())

    def add(self, revision: CatalogImportRevision) -> CatalogImportRevision:
        """Persist a new immutable revision. Callers must not mutate after flush."""
        self._session.add(revision)
        self._session.flush()
        self._session.refresh(revision)
        return revision
