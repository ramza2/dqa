"""Deterministic query normalization for Data Discovery search."""

from __future__ import annotations

import re

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_query(query: str) -> str:
    """Trim, collapse whitespace, and casefold Latin letters. No LLM rewrite."""
    collapsed = _WHITESPACE_RE.sub(" ", query.strip())
    return collapsed.casefold()


def tokenize_terms(normalized_query: str) -> list[str]:
    """Split normalized query into deterministic search terms."""
    if not normalized_query:
        return []
    parts = re.split(r"[^\w가-힣]+", normalized_query, flags=re.UNICODE)
    terms = [part for part in parts if part]
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    ordered: list[str] = []
    for term in terms:
        if term in seen:
            continue
        seen.add(term)
        ordered.append(term)
    return ordered
