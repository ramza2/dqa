"""Keyword search over revision-scoped Data Discovery documents."""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

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
    candidate_limit: int | None = None,
) -> list[KeywordHit]:
    """Score documents with bound-parameter predicates only (no SQL concat).

    Candidates are gathered in tiers so exact/original matches are not crowded
    out by expanded-term-only hits under a candidate limit:
    1) exact physical identifier
    2) original query terms
    3) terminology-expanded terms
    """
    if candidate_limit is None:
        candidate_limit = max(
            top_k * max(1, candidate_multiplier),
            max(1, candidate_min),
        )
    candidate_limit = min(_CANDIDATE_HARD_CAP, max(1, candidate_limit))

    full_cf = full_query.casefold().strip()
    original_list = _unique_terms(original_terms)
    expanded_list = _unique_terms(
        [t for t in expanded_terms if t.casefold() not in {x.casefold() for x in original_list}]
    )
    if not full_cf and not original_list and not expanded_list:
        return []

    selected: dict[int, DataDiscoveryDocument] = {}

    for doc in _fetch_exact_identifier_candidates(
        session,
        catalog_import_revision_id=catalog_import_revision_id,
        object_type=object_type,
        full_query=full_cf,
        exclude_ids=set(),
        limit=candidate_limit,
    ):
        selected[doc.id] = doc
        if len(selected) >= candidate_limit:
            break

    if len(selected) < candidate_limit and original_list:
        remaining = candidate_limit - len(selected)
        for doc in _fetch_term_candidates(
            session,
            catalog_import_revision_id=catalog_import_revision_id,
            object_type=object_type,
            terms=original_list,
            exclude_ids=set(selected),
            limit=remaining,
        ):
            selected[doc.id] = doc

    if len(selected) < candidate_limit and expanded_list:
        remaining = candidate_limit - len(selected)
        for doc in _fetch_term_candidates(
            session,
            catalog_import_revision_id=catalog_import_revision_id,
            object_type=object_type,
            terms=expanded_list,
            exclude_ids=set(selected),
            limit=remaining,
        ):
            selected[doc.id] = doc

    original_set = {t.casefold() for t in original_list if t}
    expanded_set = {t.casefold() for t in expanded_list if t}

    hits: list[KeywordHit] = []
    for doc in selected.values():
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


def _fetch_exact_identifier_candidates(
    session: Session,
    *,
    catalog_import_revision_id: int,
    object_type: str | None,
    full_query: str,
    exclude_ids: set[int],
    limit: int,
) -> list[DataDiscoveryDocument]:
    if not full_query or limit <= 0:
        return []

    conditions: list[ColumnElement[bool]] = [
        func.lower(DataDiscoveryDocument.document_key) == full_query,
        func.lower(DataDiscoveryDocument.table_name) == full_query,
        func.lower(DataDiscoveryDocument.column_name) == full_query,
    ]

    parts = full_query.split(".")
    if len(parts) == 2:
        schema, table = parts
        conditions.append(
            and_(
                func.lower(DataDiscoveryDocument.schema_name) == schema,
                func.lower(DataDiscoveryDocument.table_name) == table,
            )
        )
        conditions.append(
            func.lower(DataDiscoveryDocument.document_key)
            == f"table:{schema}.{table}"
        )
    elif len(parts) == 3:
        schema, table, column = parts
        conditions.append(
            and_(
                func.lower(DataDiscoveryDocument.schema_name) == schema,
                func.lower(DataDiscoveryDocument.table_name) == table,
                func.lower(DataDiscoveryDocument.column_name) == column,
            )
        )
        conditions.append(
            func.lower(DataDiscoveryDocument.document_key)
            == f"column:{schema}.{table}.{column}"
        )

    return _execute_candidate_query(
        session,
        catalog_import_revision_id=catalog_import_revision_id,
        object_type=object_type,
        conditions=conditions,
        exclude_ids=exclude_ids,
        limit=limit,
    )


def _fetch_term_candidates(
    session: Session,
    *,
    catalog_import_revision_id: int,
    object_type: str | None,
    terms: list[str],
    exclude_ids: set[int],
    limit: int,
) -> list[DataDiscoveryDocument]:
    if not terms or limit <= 0:
        return []

    conditions: list[ColumnElement[bool]] = []
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
    return _execute_candidate_query(
        session,
        catalog_import_revision_id=catalog_import_revision_id,
        object_type=object_type,
        conditions=conditions,
        exclude_ids=exclude_ids,
        limit=limit,
    )


def _execute_candidate_query(
    session: Session,
    *,
    catalog_import_revision_id: int,
    object_type: str | None,
    conditions: list[ColumnElement[bool]],
    exclude_ids: set[int],
    limit: int,
) -> list[DataDiscoveryDocument]:
    if not conditions or limit <= 0:
        return []
    stmt = select(DataDiscoveryDocument).where(
        DataDiscoveryDocument.catalog_import_revision_id == catalog_import_revision_id,
        or_(*conditions),
    )
    if object_type is not None:
        stmt = stmt.where(DataDiscoveryDocument.object_type == object_type)
    if exclude_ids:
        stmt = stmt.where(~DataDiscoveryDocument.id.in_(exclude_ids))
    stmt = stmt.order_by(
        DataDiscoveryDocument.document_key.asc(),
        DataDiscoveryDocument.id.asc(),
    ).limit(limit)
    return list(session.scalars(stmt).all())


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
        if re.fullmatch(r"[%\s_]+", term):
            continue
        seen.add(key)
        ordered.append(term)
    return ordered
