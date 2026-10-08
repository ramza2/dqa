"""Persistence access for Data Discovery embeddings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models.data_discovery import DataDiscoveryDocument
from app.models.data_discovery_embedding import DataDiscoveryEmbedding


@dataclass(frozen=True)
class EmbeddingCoverageStatus:
    catalog_import_revision_id: int
    model_key: str
    document_count: int
    embedding_count: int
    current_count: int
    stale_count: int
    missing_count: int

    @property
    def is_ready(self) -> bool:
        return (
            self.document_count > 0
            and self.missing_count == 0
            and self.stale_count == 0
            and self.current_count == self.document_count
        )


class DataDiscoveryEmbeddingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_revision_and_model(
        self,
        catalog_import_revision_id: int,
        model_key: str,
    ) -> list[DataDiscoveryEmbedding]:
        stmt: Select[tuple[DataDiscoveryEmbedding]] = (
            select(DataDiscoveryEmbedding)
            .join(
                DataDiscoveryDocument,
                DataDiscoveryDocument.id
                == DataDiscoveryEmbedding.data_discovery_document_id,
            )
            .where(
                DataDiscoveryDocument.catalog_import_revision_id
                == catalog_import_revision_id,
                DataDiscoveryEmbedding.model_key == model_key,
            )
        )
        return list(self._session.scalars(stmt).all())

    def map_for_revision_and_model(
        self,
        catalog_import_revision_id: int,
        model_key: str,
    ) -> dict[int, DataDiscoveryEmbedding]:
        return {
            row.data_discovery_document_id: row
            for row in self.list_for_revision_and_model(
                catalog_import_revision_id, model_key
            )
        }

    def coverage_status(
        self,
        catalog_import_revision_id: int,
        model_key: str,
    ) -> EmbeddingCoverageStatus:
        documents = list(
            self._session.scalars(
                select(DataDiscoveryDocument).where(
                    DataDiscoveryDocument.catalog_import_revision_id
                    == catalog_import_revision_id
                )
            ).all()
        )
        embeddings = self.map_for_revision_and_model(
            catalog_import_revision_id, model_key
        )
        current = 0
        stale = 0
        for doc in documents:
            emb = embeddings.get(doc.id)
            if emb is None:
                continue
            if emb.document_fingerprint == doc.document_fingerprint:
                current += 1
            else:
                stale += 1
        missing = len(documents) - current - stale
        return EmbeddingCoverageStatus(
            catalog_import_revision_id=catalog_import_revision_id,
            model_key=model_key,
            document_count=len(documents),
            embedding_count=len(embeddings),
            current_count=current,
            stale_count=stale,
            missing_count=missing,
        )

    def upsert(self, row: DataDiscoveryEmbedding) -> DataDiscoveryEmbedding:
        """Single-row upsert (SELECT per call). Prefer ``apply_to_existing_map``."""
        existing = self.map_for_revision_document(
            row.data_discovery_document_id, row.model_key
        )
        return self.apply_to_existing_map(
            {row.data_discovery_document_id: existing}
            if existing is not None
            else {},
            row,
        )

    def map_for_revision_document(
        self,
        data_discovery_document_id: int,
        model_key: str,
    ) -> DataDiscoveryEmbedding | None:
        return self._session.scalars(
            select(DataDiscoveryEmbedding).where(
                DataDiscoveryEmbedding.data_discovery_document_id
                == data_discovery_document_id,
                DataDiscoveryEmbedding.model_key == model_key,
            )
        ).first()

    def apply_to_existing_map(
        self,
        existing_by_document_id: dict[int, DataDiscoveryEmbedding],
        row: DataDiscoveryEmbedding,
    ) -> DataDiscoveryEmbedding:
        """Update or add using a preloaded revision/model map (no per-row SELECT)."""
        current = existing_by_document_id.get(row.data_discovery_document_id)
        if current is None:
            self._session.add(row)
            existing_by_document_id[row.data_discovery_document_id] = row
            return row
        current.provider = row.provider
        current.model_name = row.model_name
        current.model_revision = row.model_revision
        current.dimension = row.dimension
        current.normalized = row.normalized
        current.document_fingerprint = row.document_fingerprint
        current.embedding = row.embedding
        return current

    def count_for_revision_and_model(
        self,
        catalog_import_revision_id: int,
        model_key: str,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(DataDiscoveryEmbedding)
            .join(
                DataDiscoveryDocument,
                DataDiscoveryDocument.id
                == DataDiscoveryEmbedding.data_discovery_document_id,
            )
            .where(
                DataDiscoveryDocument.catalog_import_revision_id
                == catalog_import_revision_id,
                DataDiscoveryEmbedding.model_key == model_key,
            )
        )
        return int(self._session.scalar(stmt) or 0)
