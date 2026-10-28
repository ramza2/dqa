"""M2-3B CPU-only search-quality regression over synthetic SQLite memory data.

No real DEMIS, Oracle or PostgreSQL, and no LLM or Embedding calls.
Metrics are meaningful only for the curated synthetic label set below.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.catalog_import import CatalogImportRevision  # noqa: F401
from app.models.data_discovery import DataDiscoveryDocument
from app.services.data_discovery_search.keyword import keyword_search
from app.services.data_discovery_search.normalize import normalize_query, tokenize_terms
from app.services.data_discovery_search.terminology import expand_medical_terms

REVISION = 73
SOURCE = "synthetic_gold_only"
SCHEMA = "SYNTH"


@dataclass(frozen=True)
class GoldQuery:
    id: str
    query: str
    relevant: tuple[str, ...]
    object_type: str = "TABLE"
    expand: bool = False


GOLD = (
    GoldQuery("original_multiterm", "검사 결과",
              ("TABLE:SYNTH.Z_RESULT", "TABLE:SYNTH.Z_RESULT_SUMMARY")),
    GoldQuery("visit_multiterm", "환자 방문", ("TABLE:SYNTH.Z_VISIT",)),
    GoldQuery("clinical_multiterm", "진료 검사", ("TABLE:SYNTH.Z_CLINICAL",)),
    GoldQuery("medication_multiterm", "처방 약물", ("TABLE:SYNTH.Z_ORDER",)),
    GoldQuery("exact_table", "TB_LAB_RESULT", ("TABLE:SYNTH.TB_LAB_RESULT",)),
    GoldQuery("liver_synonym", "간수치", ("TABLE:SYNTH.Z_LIVER",), expand=True),
    GoldQuery("glucose_synonym", "혈당", ("TABLE:SYNTH.Z_GLUCOSE",), expand=True),
    GoldQuery("exact_column", "GLUCOSE",
              ("COLUMN:SYNTH.T_METRIC.GLUCOSE",), object_type="COLUMN"),
)


def _doc(table, comment, *, revision=REVISION, column=None):
    obj_type = "COLUMN" if column else "TABLE"
    physical = f"{SCHEMA}.{table}" + (f".{column}" if column else "")
    return DataDiscoveryDocument(
        catalog_import_revision_id=revision,
        source_name=SOURCE,
        schema_fingerprint="a" * 64,
        object_type=obj_type,
        identity_kind="PHYSICAL",
        schema_name=SCHEMA,
        table_name=table,
        column_name=column,
        document_key=f"{obj_type}:{physical}",
        searchable_text=comment,
        source_fingerprint="b" * 64,
        document_fingerprint="c" * 64,
        builder_version="1.0.0",
    )


def _rows():
    return [
        *[_doc(f"A_FILLER_{n:02d}", "검사 항목") for n in range(12)],
        _doc("Z_RESULT", "검사 결과"),
        _doc("Z_RESULT_SUMMARY", "검사 결과 요약"),
        _doc("Z_VISIT", "환자 방문 기록"),
        _doc("Z_CLINICAL", "진료 검사"),
        _doc("Z_ORDER", "처방 약물"),
        _doc("TB_LAB_RESULT", "liver AST ALT results"),
        _doc("Z_LIVER", "간 기능 AST ALT hepatic bilirubin panel"),
        _doc("Z_GLUCOSE", "blood glucose HbA1c glycemic"),
        _doc("T_METRIC", "glucose test result", column="GLUCOSE"),
        _doc("Z_FOREIGN_REVISION", "검사 결과", revision=REVISION + 1),
        _doc("Z_COLUMN_DISTRACTOR", "검사 결과", column="RESULT"),
    ]


def _open(*, reversed_rows=False):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DataDiscoveryDocument.__table__.create(engine)
    session = Session(engine)
    rows = _rows()
    session.add_all(list(reversed(rows)) if reversed_rows else rows)
    session.flush()
    return engine, session


def _search(session, case):
    normalized = normalize_query(case.query)
    expanded = (expand_medical_terms(normalized).expanded_terms if case.expand else [])
    hits = keyword_search(
        session, catalog_import_revision_id=REVISION,
        original_terms=tokenize_terms(normalized),
        expanded_terms=expanded,
        full_query=normalized, object_type=case.object_type,
        top_k=3, candidate_multiplier=1, candidate_min=1,
        candidate_limit=3,
    )
    assert all(hit.document.catalog_import_revision_id == REVISION for hit in hits)
    assert all(hit.document.object_type == case.object_type for hit in hits)
    return [hit.document.document_key for hit in hits]


def recall_at_k(keys, relevant, k):
    if k <= 0 or not relevant or len(set(relevant)) != len(relevant):
        raise ValueError("invalid gold recall inputs")
    return len(set(keys[:k]) & set(relevant)) / len(relevant)


def reciprocal_rank_at_k(keys, relevant, k):
    if k <= 0 or not relevant:
        raise ValueError("invalid gold MRR inputs")
    for index, key in enumerate(keys[:k], start=1):
        if key in relevant:
            return 1.0 / index
    return 0.0


def test_gold_recall_and_mrr_with_report():
    engine, session = _open()
    try:
        r1_scores, r3_scores, rr3_scores = [], [], []
        for case in GOLD:
            keys = _search(session, case)
            r1 = recall_at_k(keys, case.relevant, 1)
            r3 = recall_at_k(keys, case.relevant, 3)
            rr3 = reciprocal_rank_at_k(keys, case.relevant, 3)
            r1_scores.append(r1)
            r3_scores.append(r3)
            rr3_scores.append(rr3)
            assert r3 == 1.0, f"{case.id}: missing gold key; ranked={keys}"
            assert rr3 == 1.0, f"{case.id}: expected relevant rank 1; ranked={keys}"
            print(f"M2_3B_QUERY={case.id} R1={r1:.3f} R3={r3:.3f} RR3={rr3:.3f}")
        assert len(GOLD) == 8
        assert mean(r1_scores) >= 0.93
        assert mean(r3_scores) == 1.0
        assert mean(rr3_scores) == 1.0
        print(f"M2_3B_GOLD_SUMMARY=queries:{len(GOLD)} "
              f"macro_R1:{mean(r1_scores):.3f} "
              f"macro_R3:{mean(r3_scores):.3f} "
              f"MRR3:{mean(rr3_scores):.3f}")
    finally:
        session.close()
        engine.dispose()


def test_rankings_are_stable_when_insertion_order_is_reversed():
    engine_a, session_a = _open()
    engine_b, session_b = _open(reversed_rows=True)
    try:
        for case in GOLD:
            assert _search(session_a, case) == _search(session_b, case), case.id
    finally:
        session_a.close()
        session_b.close()
        engine_a.dispose()
        engine_b.dispose()


def test_no_results_for_absent_query_or_other_revision_only():
    engine, session = _open()
    try:
        for query in ("존재하지않는용어", "Z_FOREIGN_REVISION"):
            assert _search(session, GoldQuery("negative", query, ())) == []
    finally:
        session.close()
        engine.dispose()


def test_metric_definitions_and_invalid_gold_rejected():
    relevant = ("T:A", "T:B")
    ranked = ["T:WRONG", "T:B", "T:A"]
    assert recall_at_k(ranked, relevant, 1) == 0.0
    assert recall_at_k(ranked, relevant, 2) == 0.5
    assert recall_at_k(ranked, relevant, 3) == 1.0
    assert reciprocal_rank_at_k(ranked, relevant, 1) == 0.0
    assert reciprocal_rank_at_k(ranked, relevant, 2) == 0.5
    assert reciprocal_rank_at_k(ranked, relevant, 3) == 0.5
    for keys in ((), ("T:A", "T:A")):
        with pytest.raises(ValueError):
            recall_at_k([], keys, 3)
    with pytest.raises(ValueError):
        reciprocal_rank_at_k(ranked, relevant, 0)
