"""Data Discovery schema search orchestration (Phase 27-B)."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode
from app.adapters.embedding.base import EmbeddingProvider
from app.core.config import Settings, get_settings
from app.domain.data_discovery import DataDiscoverySearchMode, DiscoveryObjectType
from app.models.data_discovery import DataDiscoveryDocument
from app.repositories.data_discovery import DataDiscoveryRepository
from app.schemas.data_discovery import (
    DataDiscoveryRelationHopModel,
    DataDiscoveryRelatedTableModel,
    DataDiscoverySearchRequest,
    DataDiscoverySearchResponse,
    DataDiscoverySearchResultItem,
    DataDiscoverySearchTimings,
    PhysicalDiscoveryIdentityModel,
)
from app.services.catalog_query import resolve_active_revision
from app.services.data_discovery_search.keyword import keyword_search
from app.services.data_discovery_search.normalize import normalize_query, tokenize_terms
from app.services.data_discovery_search.relation import expand_relations
from app.services.data_discovery_search.rrf import RankedItem, reciprocal_rank_fusion
from app.services.data_discovery_search.semantic import semantic_search
from app.services.data_discovery_search.terminology import expand_medical_terms

_SNIPPET_MAX = 280


def search_schema(
    session: Session,
    request: DataDiscoverySearchRequest,
    *,
    embedding_provider: EmbeddingProvider | None = None,
    settings: Settings | None = None,
) -> DataDiscoverySearchResponse:
    """Execute keyword / semantic / hybrid search against the active revision."""
    cfg = settings or get_settings()
    started = time.perf_counter()

    resolved = resolve_active_revision(session, request.source_name)
    revision = resolved.revision

    doc_count = DataDiscoveryRepository(session).count_for_revision(revision.id)
    if doc_count <= 0:
        raise DataDiscoveryError(
            DataDiscoveryErrorCode.DISCOVERY_INDEX_NOT_READY,
            "discovery documents are not ready for the active catalog revision",
        )

    mode = _coerce_mode(request.mode)
    object_type = _coerce_object_type(request.object_type)

    original_query = request.query
    normalized = normalize_query(original_query)
    original_terms = tokenize_terms(normalized)

    matched_concepts: list[str] = []
    expanded_terms: list[str] = []
    if request.expand_terms:
        expansion = expand_medical_terms(
            normalized,
            terms_path=cfg.data_discovery_medical_terms_path,
        )
        matched_concepts = list(expansion.matched_concepts)
        expanded_terms = list(expansion.expanded_terms)

    expanded_query_terms = _unique([*original_terms, *[t.casefold() for t in expanded_terms]])
    expanded_query = " ".join(expanded_query_terms)

    candidate_limit = min(
        500,
        max(
            request.top_k * max(1, cfg.data_discovery_search_candidate_multiplier),
            max(1, cfg.data_discovery_search_candidate_min),
        ),
    )

    keyword_ms = 0.0
    semantic_ms = 0.0
    keyword_hits = []
    semantic_hits = []
    model_key: str | None = None

    if mode in {DataDiscoverySearchMode.KEYWORD, DataDiscoverySearchMode.HYBRID}:
        t0 = time.perf_counter()
        keyword_hits = keyword_search(
            session,
            catalog_import_revision_id=revision.id,
            original_terms=original_terms,
            expanded_terms=expanded_terms,
            full_query=normalized,
            object_type=object_type,
            top_k=request.top_k,
            candidate_multiplier=cfg.data_discovery_search_candidate_multiplier,
            candidate_min=cfg.data_discovery_search_candidate_min,
        )
        keyword_ms = (time.perf_counter() - t0) * 1000.0

    if mode in {DataDiscoverySearchMode.SEMANTIC, DataDiscoverySearchMode.HYBRID}:
        if embedding_provider is None:
            raise DataDiscoveryError(
                DataDiscoveryErrorCode.EMBEDDING_NOT_CONFIGURED,
                "embedding provider is not configured",
            )
        model_key = embedding_provider.model_key
        t0 = time.perf_counter()
        semantic_hits = semantic_search(
            session,
            catalog_import_revision_id=revision.id,
            provider=embedding_provider,
            query=normalized,
            object_type=object_type,
            candidate_limit=candidate_limit,
        )
        semantic_ms = (time.perf_counter() - t0) * 1000.0

    results: list[DataDiscoverySearchResultItem]
    if mode is DataDiscoverySearchMode.KEYWORD:
        results = [
            _result_item(
                rank=index,
                document=hit.document,
                source_name=resolved.source_name,
                revision_id=revision.id,
                schema_fingerprint=resolved.schema_fingerprint,
                keyword_score=hit.score,
                keyword_rank=index,
                evidence=list(hit.evidence),
            )
            for index, hit in enumerate(keyword_hits[: request.top_k], start=1)
        ]
    elif mode is DataDiscoverySearchMode.SEMANTIC:
        results = [
            _result_item(
                rank=index,
                document=hit.document,
                source_name=resolved.source_name,
                revision_id=revision.id,
                schema_fingerprint=resolved.schema_fingerprint,
                semantic_score=hit.score,
                semantic_rank=index,
                evidence=["semantic_cosine"],
            )
            for index, hit in enumerate(semantic_hits[: request.top_k], start=1)
        ]
    else:
        semantic_ranked = [
            RankedItem(
                key=hit.document.document_key,
                payload=hit.document,
                rank=index,
                score=hit.score,
            )
            for index, hit in enumerate(semantic_hits, start=1)
        ]
        keyword_ranked = [
            RankedItem(
                key=hit.document.document_key,
                payload=hit.document,
                rank=index,
                score=hit.score,
            )
            for index, hit in enumerate(keyword_hits, start=1)
        ]
        fused = reciprocal_rank_fusion(
            semantic_items=semantic_ranked,
            keyword_items=keyword_ranked,
            k=cfg.data_discovery_search_rrf_k,
        )[: request.top_k]
        results = [
            _result_item(
                rank=index,
                document=item.payload,  # type: ignore[arg-type]
                source_name=resolved.source_name,
                revision_id=revision.id,
                schema_fingerprint=resolved.schema_fingerprint,
                semantic_score=item.semantic_score,
                semantic_rank=item.semantic_rank,
                keyword_score=item.keyword_score,
                keyword_rank=item.keyword_rank,
                rrf_score=item.rrf_score,
                evidence=["rrf_hybrid"],
            )
            for index, item in enumerate(fused, start=1)
        ]

    related_tables: list[DataDiscoveryRelatedTableModel] = []
    if request.expand_relations and request.max_relation_hops > 0:
        seeds = _seed_tables(results)
        related = expand_relations(
            revision,
            seed_tables=seeds,
            max_hops=request.max_relation_hops,
        )
        related_tables = [
            DataDiscoveryRelatedTableModel(
                schema_name=item.schema_name,
                table_name=item.table_name,
                hop_distance=item.hop_distance,
                seed_schema=item.seed_schema,
                seed_table=item.seed_table,
                path=[
                    DataDiscoveryRelationHopModel(
                        from_schema=hop.from_schema,
                        from_table=hop.from_table,
                        to_schema=hop.to_schema,
                        to_table=hop.to_table,
                        constraint_name=hop.constraint_name,
                        direction=hop.direction,
                        from_columns=list(hop.from_columns),
                        to_columns=list(hop.to_columns),
                    )
                    for hop in item.path
                ],
            )
            for item in related
        ]

    total_ms = (time.perf_counter() - started) * 1000.0
    return DataDiscoverySearchResponse(
        source_name=resolved.source_name,
        catalog_revision_id=revision.id,
        schema_fingerprint=resolved.schema_fingerprint,
        mode=mode.value,
        model_key=model_key,
        original_query=original_query,
        normalized_query=normalized,
        expanded_query=expanded_query,
        matched_concepts=matched_concepts,
        expanded_terms=expanded_terms,
        results=results,
        related_tables=related_tables,
        timings=DataDiscoverySearchTimings(
            keyword_ms=keyword_ms,
            semantic_ms=semantic_ms,
            total_ms=total_ms,
        ),
    )


def _result_item(
    *,
    rank: int,
    document: DataDiscoveryDocument,
    source_name: str,
    revision_id: int,
    schema_fingerprint: str,
    semantic_score: float | None = None,
    semantic_rank: int | None = None,
    keyword_score: float | None = None,
    keyword_rank: int | None = None,
    rrf_score: float | None = None,
    evidence: list[str] | None = None,
) -> DataDiscoverySearchResultItem:
    return DataDiscoverySearchResultItem(
        rank=rank,
        identity=PhysicalDiscoveryIdentityModel(
            source_name=source_name,
            catalog_revision_id=revision_id,
            schema_fingerprint=schema_fingerprint,
            schema_name=document.schema_name,
            table_name=document.table_name,
            column_name=document.column_name,
        ),
        document_key=document.document_key,
        object_type=document.object_type,  # type: ignore[arg-type]
        semantic_score=semantic_score,
        semantic_rank=semantic_rank,
        keyword_score=keyword_score,
        keyword_rank=keyword_rank,
        rrf_score=rrf_score,
        evidence=evidence or [],
        evidence_snippet=_snippet(document.searchable_text),
    )


def _snippet(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _SNIPPET_MAX:
        return collapsed
    return collapsed[: _SNIPPET_MAX - 1] + "…"


def _seed_tables(
    results: list[DataDiscoverySearchResultItem],
) -> list[tuple[str, str]]:
    seeds: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in results:
        key = (item.identity.schema_name, item.identity.table_name)
        if key in seen:
            continue
        seen.add(key)
        seeds.append(key)
    return seeds


def _coerce_mode(value: Any) -> DataDiscoverySearchMode:
    if isinstance(value, DataDiscoverySearchMode):
        return value
    try:
        return DataDiscoverySearchMode(str(value))
    except ValueError as exc:
        raise DataDiscoveryError(
            DataDiscoveryErrorCode.INVALID_SEARCH_MODE,
            "invalid search mode",
        ) from exc


def _coerce_object_type(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, DiscoveryObjectType):
        return value.value
    text = str(value)
    if text not in {DiscoveryObjectType.TABLE.value, DiscoveryObjectType.COLUMN.value}:
        raise DataDiscoveryError(
            DataDiscoveryErrorCode.INVALID_OBJECT_TYPE,
            "invalid object type filter",
        )
    return text


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
