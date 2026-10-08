"""Persistence access for revision-scoped Data Discovery documents."""

from __future__ import annotations

from sqlalchemy import Select, delete, select
from sqlalchemy.orm import Session

from app.models.data_discovery import DataDiscoveryDocument


class DataDiscoveryRepository:
    """CRUD helpers for DataDiscoveryDocument within one Catalog revision."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_revision(
        self, catalog_import_revision_id: int
    ) -> list[DataDiscoveryDocument]:
        stmt: Select[tuple[DataDiscoveryDocument]] = (
            select(DataDiscoveryDocument)
            .where(
                DataDiscoveryDocument.catalog_import_revision_id
                == catalog_import_revision_id
            )
            .order_by(
                DataDiscoveryDocument.document_key.asc(),
                DataDiscoveryDocument.id.asc(),
            )
        )
        return list(self._session.scalars(stmt).all())

    def count_for_revision(self, catalog_import_revision_id: int) -> int:
        return len(self.list_for_revision(catalog_import_revision_id))

    def get_by_revision_and_key(
        self,
        catalog_import_revision_id: int,
        document_key: str,
    ) -> DataDiscoveryDocument | None:
        stmt = select(DataDiscoveryDocument).where(
            DataDiscoveryDocument.catalog_import_revision_id
            == catalog_import_revision_id,
            DataDiscoveryDocument.document_key == document_key,
        )
        return self._session.scalars(stmt).first()

    def upsert(self, document: DataDiscoveryDocument) -> DataDiscoveryDocument:
        """Insert or update by (revision_id, document_key). Caller owns commit."""
        existing = self.get_by_revision_and_key(
            document.catalog_import_revision_id,
            document.document_key,
        )
        if existing is None:
            self._session.add(document)
            self._session.flush()
            self._session.refresh(document)
            return document

        existing.source_name = document.source_name
        existing.schema_fingerprint = document.schema_fingerprint
        existing.object_type = document.object_type
        existing.identity_kind = document.identity_kind
        existing.schema_name = document.schema_name
        existing.table_name = document.table_name
        existing.column_name = document.column_name
        existing.searchable_text = document.searchable_text
        existing.source_fingerprint = document.source_fingerprint
        existing.document_fingerprint = document.document_fingerprint
        existing.builder_version = document.builder_version
        self._session.flush()
        self._session.refresh(existing)
        return existing

    def delete_for_revision_except_keys(
        self,
        catalog_import_revision_id: int,
        keep_document_keys: set[str],
    ) -> int:
        """Remove stale derived documents for one revision only."""
        stmt = select(DataDiscoveryDocument.id, DataDiscoveryDocument.document_key).where(
            DataDiscoveryDocument.catalog_import_revision_id
            == catalog_import_revision_id
        )
        stale_ids = [
            row.id
            for row in self._session.execute(stmt).all()
            if row.document_key not in keep_document_keys
        ]
        if not stale_ids:
            return 0
        self._session.execute(
            delete(DataDiscoveryDocument).where(DataDiscoveryDocument.id.in_(stale_ids))
        )
        self._session.flush()
        return len(stale_ids)
