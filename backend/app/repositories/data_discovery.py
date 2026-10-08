"""Persistence access for revision-scoped Data Discovery documents."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from app.models.data_discovery import DataDiscoveryDocument


@dataclass(frozen=True)
class ReconcileResult:
    upserted_count: int
    deleted_count: int


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
        stmt = (
            select(func.count())
            .select_from(DataDiscoveryDocument)
            .where(
                DataDiscoveryDocument.catalog_import_revision_id
                == catalog_import_revision_id
            )
        )
        return int(self._session.scalar(stmt) or 0)

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

    def reconcile_for_revision(
        self,
        catalog_import_revision_id: int,
        documents: list[DataDiscoveryDocument],
    ) -> ReconcileResult:
        """Authoritative replace of derived documents for one revision.

        Loads existing rows once, applies in-memory upserts, deletes stale keys
        scoped to ``catalog_import_revision_id``, then flushes once.
        """
        existing = {
            doc.document_key: doc
            for doc in self.list_for_revision(catalog_import_revision_id)
        }
        keep_keys: set[str] = set()
        upserted = 0

        for document in documents:
            if document.catalog_import_revision_id != catalog_import_revision_id:
                raise ValueError(
                    "document revision id does not match reconcile revision scope"
                )
            keep_keys.add(document.document_key)
            current = existing.get(document.document_key)
            if current is None:
                self._session.add(document)
            else:
                current.source_name = document.source_name
                current.schema_fingerprint = document.schema_fingerprint
                current.object_type = document.object_type
                current.identity_kind = document.identity_kind
                current.schema_name = document.schema_name
                current.table_name = document.table_name
                current.column_name = document.column_name
                current.searchable_text = document.searchable_text
                current.source_fingerprint = document.source_fingerprint
                current.document_fingerprint = document.document_fingerprint
                current.builder_version = document.builder_version
            upserted += 1

        stale_ids = [
            doc.id for key, doc in existing.items() if key not in keep_keys
        ]
        deleted = 0
        if stale_ids:
            self._session.execute(
                delete(DataDiscoveryDocument).where(
                    DataDiscoveryDocument.catalog_import_revision_id
                    == catalog_import_revision_id,
                    DataDiscoveryDocument.id.in_(stale_ids),
                )
            )
            deleted = len(stale_ids)

        self._session.flush()
        return ReconcileResult(upserted_count=upserted, deleted_count=deleted)
