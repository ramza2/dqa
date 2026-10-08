"""Incremental embedding sync for revision-scoped Data Discovery documents."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.adapters.catalog.activation_errors import (
    CatalogActivationError,
    CatalogActivationErrorCode,
)
from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode
from app.adapters.embedding.base import EmbeddingProvider
from app.models.data_discovery_embedding import (
    EMBEDDING_VECTOR_DIMENSION,
    DataDiscoveryEmbedding,
)
from app.repositories.catalog_import import CatalogImportRepository
from app.repositories.data_discovery import DataDiscoveryRepository
from app.repositories.data_discovery_embedding import (
    DataDiscoveryEmbeddingRepository,
    EmbeddingCoverageStatus,
)


@dataclass(frozen=True)
class EmbeddingSyncResult:
    catalog_import_revision_id: int
    model_key: str
    document_count: int
    embedded_count: int
    skipped_count: int


def sync_embeddings_for_revision(
    session: Session,
    revision_id: int,
    provider: EmbeddingProvider,
    *,
    batch_size: int = 16,
) -> EmbeddingSyncResult:
    """Embed missing/stale documents for one revision and one model_key.

    Caller owns the transaction/commit. Does not touch other revisions or
    other model_key rows.
    """
    revision = CatalogImportRepository(session).get_by_id(revision_id)
    if revision is None:
        raise CatalogActivationError(
            CatalogActivationErrorCode.IMPORT_NOT_FOUND,
            "import revision not found",
        )
    if provider.dimension != EMBEDDING_VECTOR_DIMENSION:
        raise DataDiscoveryError(
            DataDiscoveryErrorCode.EMBEDDING_DIMENSION_MISMATCH,
            "embedding dimension is not supported by this implementation",
        )

    documents = DataDiscoveryRepository(session).list_for_revision(revision.id)
    emb_repo = DataDiscoveryEmbeddingRepository(session)
    existing = emb_repo.map_for_revision_and_model(revision.id, provider.model_key)

    to_embed = [
        doc
        for doc in documents
        if existing.get(doc.id) is None
        or existing[doc.id].document_fingerprint != doc.document_fingerprint
    ]
    skipped = len(documents) - len(to_embed)
    embedded = 0

    size = max(1, batch_size)
    for offset in range(0, len(to_embed), size):
        batch = to_embed[offset : offset + size]
        vectors = provider.embed_documents([doc.searchable_text for doc in batch])
        if len(vectors) != len(batch):
            raise DataDiscoveryError(
                DataDiscoveryErrorCode.EMBEDDING_INVALID_RESPONSE,
                "embedding provider returned unexpected vector count",
            )
        for doc, vector in zip(batch, vectors, strict=True):
            if len(vector) != EMBEDDING_VECTOR_DIMENSION:
                raise DataDiscoveryError(
                    DataDiscoveryErrorCode.EMBEDDING_DIMENSION_MISMATCH,
                    "embedding provider vector dimension mismatch",
                )
            emb_repo.apply_to_existing_map(
                existing,
                DataDiscoveryEmbedding(
                    data_discovery_document_id=doc.id,
                    model_key=provider.model_key,
                    provider=provider.provider_name,
                    model_name=provider.model_name,
                    model_revision=provider.model_revision,
                    dimension=provider.dimension,
                    normalized=provider.normalized,
                    document_fingerprint=doc.document_fingerprint,
                    embedding=list(vector),
                ),
            )
            embedded += 1

    session.flush()
    return EmbeddingSyncResult(
        catalog_import_revision_id=revision.id,
        model_key=provider.model_key,
        document_count=len(documents),
        embedded_count=embedded,
        skipped_count=skipped,
    )


def embedding_status_for_revision(
    session: Session,
    revision_id: int,
    model_key: str,
) -> EmbeddingCoverageStatus:
    return DataDiscoveryEmbeddingRepository(session).coverage_status(
        revision_id, model_key
    )
