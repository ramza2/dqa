"""Exact cosine semantic search over revision-scoped embeddings."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode
from app.adapters.embedding.base import EmbeddingProvider
from app.models.data_discovery import DataDiscoveryDocument
from app.models.data_discovery_embedding import DataDiscoveryEmbedding
from app.repositories.data_discovery_embedding import DataDiscoveryEmbeddingRepository


@dataclass(frozen=True)
class SemanticHit:
    document: DataDiscoveryDocument
    score: float
    distance: float


def semantic_search(
    session: Session,
    *,
    catalog_import_revision_id: int,
    provider: EmbeddingProvider,
    query: str,
    object_type: str | None,
    candidate_limit: int,
) -> list[SemanticHit]:
    status = DataDiscoveryEmbeddingRepository(session).coverage_status(
        catalog_import_revision_id, provider.model_key
    )
    if not status.is_ready:
        raise DataDiscoveryError(
            DataDiscoveryErrorCode.EMBEDDING_NOT_READY,
            "embedding index is not ready for the active catalog revision",
        )

    query_vectors = provider.embed_queries([query])
    if not query_vectors:
        raise DataDiscoveryError(
            DataDiscoveryErrorCode.EMBEDDING_INVALID_RESPONSE,
            "embedding provider returned unexpected vector count",
        )
    query_vector = query_vectors[0]

    distance_expr = DataDiscoveryEmbedding.embedding.cosine_distance(query_vector)
    stmt = (
        select(DataDiscoveryDocument, DataDiscoveryEmbedding, distance_expr)
        .join(
            DataDiscoveryEmbedding,
            DataDiscoveryEmbedding.data_discovery_document_id
            == DataDiscoveryDocument.id,
        )
        .where(
            DataDiscoveryDocument.catalog_import_revision_id
            == catalog_import_revision_id,
            DataDiscoveryEmbedding.model_key == provider.model_key,
            DataDiscoveryEmbedding.document_fingerprint
            == DataDiscoveryDocument.document_fingerprint,
        )
    )
    if object_type is not None:
        stmt = stmt.where(DataDiscoveryDocument.object_type == object_type)
    stmt = stmt.order_by(
        distance_expr.asc(),
        DataDiscoveryDocument.document_key.asc(),
        DataDiscoveryDocument.id.asc(),
    ).limit(candidate_limit)

    hits: list[SemanticHit] = []
    for document, _embedding, distance in session.execute(stmt).all():
        dist = float(distance)
        score = max(0.0, 1.0 - dist)
        hits.append(SemanticHit(document=document, score=score, distance=dist))
    return hits
