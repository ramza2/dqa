"""Reciprocal Rank Fusion for hybrid Data Discovery search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class RankedItem:
    key: str
    payload: object
    rank: int
    score: float


@dataclass(frozen=True)
class FusedItem:
    key: str
    payload: object
    rrf_score: float
    semantic_rank: int | None
    semantic_score: float | None
    keyword_rank: int | None
    keyword_score: float | None


def reciprocal_rank_fusion(
    *,
    semantic_items: list[RankedItem],
    keyword_items: list[RankedItem],
    k: int = 60,
) -> list[FusedItem]:
    """Fuse two ranked lists by RRF. Deterministic tie-break on key."""
    k = max(1, k)
    fused: dict[str, FusedItem] = {}

    for item in semantic_items:
        current = fused.get(item.key)
        contrib = 1.0 / (k + item.rank)
        if current is None:
            fused[item.key] = FusedItem(
                key=item.key,
                payload=item.payload,
                rrf_score=contrib,
                semantic_rank=item.rank,
                semantic_score=item.score,
                keyword_rank=None,
                keyword_score=None,
            )
        else:
            fused[item.key] = FusedItem(
                key=item.key,
                payload=current.payload,
                rrf_score=current.rrf_score + contrib,
                semantic_rank=item.rank,
                semantic_score=item.score,
                keyword_rank=current.keyword_rank,
                keyword_score=current.keyword_score,
            )

    for item in keyword_items:
        current = fused.get(item.key)
        contrib = 1.0 / (k + item.rank)
        if current is None:
            fused[item.key] = FusedItem(
                key=item.key,
                payload=item.payload,
                rrf_score=contrib,
                semantic_rank=None,
                semantic_score=None,
                keyword_rank=item.rank,
                keyword_score=item.score,
            )
        else:
            fused[item.key] = FusedItem(
                key=item.key,
                payload=current.payload,
                rrf_score=current.rrf_score + contrib,
                semantic_rank=current.semantic_rank,
                semantic_score=current.semantic_score,
                keyword_rank=item.rank,
                keyword_score=item.score,
            )

    return sorted(
        fused.values(),
        key=lambda item: (-item.rrf_score, item.key),
    )
