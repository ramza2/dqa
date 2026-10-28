"""M2-3A: CPU-only keyword search candidate priority with synthetic SQLite data.

No real Oracle/DEMIS/production PostgreSQL, HTTP, embeddings, or SQL templates.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Ensure SQLAlchemy can resolve the Catalog revision FK for local table DDL.
from app.models.catalog_import import CatalogImportRevision  # noqa: F401
from app.models.data_discovery import DataDiscoveryDocument
from app.services.data_discovery_search.keyword import keyword_search

REVISION = 17


def _document(name: str, searchable_text: str, *, revision: int = REVISION,
              object_type: str = "TABLE") -> DataDiscoveryDocument:
    return DataDiscoveryDocument(
        catalog_import_revision_id=revision,
        source_name="synthetic_catalog",
        schema_fingerprint="a" * 64,
        object_type=object_type,
        identity_kind="PHYSICAL",
        schema_name="SYNTH",
        table_name=name,
        column_name=None,
        document_key=f"TABLE:SYNTH.{name}",
        searchable_text=searchable_text,
        source_fingerprint="b" * 64,
        document_fingerprint="c" * 64,
        builder_version="1.0.0",
    )


def _session_with_rows():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    DataDiscoveryDocument.__table__.create(engine)
    session = Session(engine)
    return engine, session


def _hits(session: Session, terms: list[str], *, candidate_limit: int = 3,
          expanded_terms: list[str] | None = None):
    return keyword_search(
        session, catalog_import_revision_id=REVISION,
        original_terms=terms, expanded_terms=expanded_terms or [],
        full_query=" ".join(terms), object_type="TABLE", top_k=3,
        candidate_multiplier=1, candidate_min=1,
        candidate_limit=candidate_limit,
    )


def test_multiterm_match_retained_under_candidate_cap_without_embeddings():
    engine, session = _session_with_rows()
    try:
        # Earlier alphabetical one-term hits would consume all slots.
        for i in range(5):
            session.add(_document(f"A_FILLER_{i:02d}", "검사 항목"))
        session.add(_document("Z_RELEVANT", "검사 결과"))
        session.flush()

        hits = _hits(session, ["검사", "결과"])
        keys = [hit.document.table_name for hit in hits]
        assert len(keys) == 3
        assert keys[0] == "Z_RELEVANT"
        assert "Z_RELEVANT" in keys
        assert all(hit.score > 0 for hit in hits)
        assert any("multi_term_bonus" in hit.evidence for hit in hits
                   if hit.document.table_name == "Z_RELEVANT")
    finally:
        session.close()
        engine.dispose()


def test_original_multiterm_matches_before_expansion_only_even_with_cap():
    engine, session = _session_with_rows()
    try:
        for i in range(6):
            session.add(_document(f"A_EXPANDED_{i:02d}", "간수치 hepatic liver"))
        session.add(_document("Z_ORIGINAL", "진료 검사"))
        session.flush()
        hits = _hits(session, ["진료", "검사"], candidate_limit=2,
                     expanded_terms=["hepatic", "liver"])
        assert hits[0].document.table_name == "Z_ORIGINAL"
        assert len(hits) <= 2
    finally:
        session.close()
        engine.dispose()


def test_single_token_exact_identifier_and_revision_scope_are_unchanged():
    engine, session = _session_with_rows()
    try:
        session.add(_document("TB_LAB", "검사"))
        session.add(_document("A_FILLER", "검사"))
        session.add(_document("ZZ_EXTERNAL", "검사", revision=99))
        session.flush()

        hits = _hits(session, ["tb_lab"], candidate_limit=1)
        assert [hit.document.table_name for hit in hits] == ["TB_LAB"]
        assert all(hit.document.catalog_import_revision_id == REVISION for hit in hits)
    finally:
        session.close()
        engine.dispose()


def test_multiterm_escaped_wildcards_are_literal_not_pattern_wildcards():
    engine, session = _session_with_rows()
    try:
        session.add(_document("A_UNRELATED", "AB1XX 검사"))
        session.add(_document("Z_LITERAL", "AB_% 검사"))
        session.flush()

        hits = _hits(session, ["ab_%", "검사"], candidate_limit=1)
        assert [hit.document.table_name for hit in hits] == ["Z_LITERAL"]
    finally:
        session.close()
        engine.dispose()


def test_long_term_list_stays_bounded_and_retains_legacy_or_search():
    engine, session = _session_with_rows()
    try:
        session.add(_document("Z_ONE_TERM", "여섯"))
        session.flush()
        hits = _hits(session, ["하나", "둘", "셋", "넷", "다섯", "여섯", "일곱"],
                     candidate_limit=2)
        assert [hit.document.table_name for hit in hits] == ["Z_ONE_TERM"]
    finally:
        session.close()
        engine.dispose()
