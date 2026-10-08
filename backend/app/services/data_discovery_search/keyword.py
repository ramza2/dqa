"""Keyword search over revision-scoped Data Discovery documents."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.data_discovery import DataDiscoveryDocument

_CANDIDATE_HARD_CAP = 500
_ILIKE_ESCAPE = "\\"


@dataclass(frozen=True)
class KeywordHit:
    document: DataDiscoveryDocument
    score: float
    evidence: tuple[str, ...]


def keyword_search(
    session: Session,
    *,
    catalog_import_revision_id: int,
    original_terms: list[str],
    expanded_terms: list[str],
    full_query: str,
    object_type: str | None,
    top_k: int,
    candidate_multiplier: int,
    candidate_min: int,
) -> list[KeywordHit]:
    """Score documents with bound-parameter predicates only (no SQL concat)."""
    terms = _unique_terms([*original_terms, *expanded_terms, full_query])
    if not terms:
        return []

    candidate_limit = min(
        _CANDIDATE_HARD_CAP,
        max(top_k * max(1, candidate_multiplier), max(1, candidate_min)),
    )

    conditions = []
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        conditions.extend(
            [
                DataDiscoveryDocument.document_key.ilike(pattern, escape=_ILIKE_ESCAPE),
                DataDiscoveryDocument.schema_name.ilike(pattern, escape=_ILIKE_ESCAPE),
                DataDiscoveryDocument.table_name.ilike(pattern, escape=_ILIKE_ESCAPE),
                DataDiscoveryDocument.column_name.ilike(pattern, escape=_ILIKE_ESCAPE),
                DataDiscoveryDocument.searchable_text.ilike(pattern, escape=_ILIKE_ESCAPE),
            ]
        )

    stmt = select(DataDiscoveryDocument).where(
        DataDiscoveryDocument.catalog_import_revision_id == catalog_import_revision_id,
        or_(*conditions),
    )
    if object_type is not None:
        stmt = stmt.where(DataDiscoveryDocument.object_type == object_type)
    stmt = stmt.order_by(
        DataDiscoveryDocument.document_key.asc(),
        DataDiscoveryDocument.id.asc(),
    ).limit(candidate_limit)

    documents = list(session.scalars(stmt).all())
    original_set = {t.casefold() for t in original_terms if t}
    expanded_set = {
        t.casefold() for t in expanded_terms if t and t.casefold() not in original_set
    }
    full_cf = full_query.casefold().strip()

    hits: list[KeywordHit] = []
    for doc in documents:
        score, evidence = _score_document(
            doc,
            original_terms=original_set,
            expanded_terms=expanded_set,
            full_query=full_cf,
        )
        if score <= 0:
            continue
        hits.append(KeywordHit(document=doc, score=score, evidence=tuple(evidence)))

    hits.sort(key=lambda h: (-h.score, h.document.document_key, h.document.id))
    return hits[:candidate_limit]


def _score_document(
    doc: DataDiscoveryDocument,
    *,
    original_terms: set[str],
    expanded_terms: set[str],
    full_query: str,
) -> tuple[float, list[str]]:
    score = 0.0
    evidence: list[str] = []
    schema = doc.schema_name.casefold()
    table = doc.table_name.casefold()
    column = (doc.column_name or "").casefold()
    key = doc.document_key.casefold()
    text = doc.searchable_text.casefold()
    if full_query:
        if full_query == key:
            score += 120.0
            evidence.append("exact_document_key")
        elif column and full_query == f"{schema}.{table}.{column}":
            score += 110.0
            evidence.append("exact_column_identifier")
        elif full_query == f"{schema}.{table}" and doc.object_type == "TABLE":
            score += 100.0
            evidence.append("exact_table_identifier")
        elif full_query == table and doc.object_type == "TABLE":
            score += 95.0
            evidence.append("exact_table_name")
        elif column and full_query == column and doc.object_type == "COLUMN":
            score += 95.0
            evidence.append("exact_column_name")

    for term in sorted(original_terms):
        if not term:
            continue
        if term == key:
            score += 50.0
            evidence.append(f"original_identifier:{term}")
        elif doc.object_type == "TABLE" and term == table:
            score += 50.0
            evidence.append(f"original_identifier:{term}")
        elif doc.object_type == "COLUMN" and column and term == column:
            score += 50.0
            evidence.append(f"original_identifier:{term}")
        elif term in key or term in text or term == schema or term == table:
            score += 12.0
            evidence.append(f"original_term:{term}")

    for term in sorted(expanded_terms):
        if not term:
            continue
        if term in key or term in text or term == table or term == column:
            score += 3.0
            evidence.append(f"expanded_term:{term}")

    # Lightweight FTS-style bonus using PostgreSQL simple tokenization is optional;
    # keep an additional bounded bonus when multiple original terms match.
    matched_original = sum(
        1 for term in original_terms if term and (term in text or term in key)
    )
    if matched_original >= 2:
        score += 5.0
        evidence.append("multi_term_bonus")

    return score, evidence


def _escape_like(value: str) -> str:
    return (
        value.replace(_ILIKE_ESCAPE, _ILIKE_ESCAPE + _ILIKE_ESCAPE)
        .replace("%", _ILIKE_ESCAPE + "%")
        .replace("_", _ILIKE_ESCAPE + "_")
    )


def _unique_terms(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        term = value.strip()
        if not term:
            continue
        key = term.casefold()
        if key in seen:
            continue
        # Reject pathological terms that are only wildcards after escape.
        if re.fullmatch(r"[%\s_]+", term):
            continue
        seen.add(key)
        ordered.append(term)
    return ordered
