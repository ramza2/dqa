"""S-06-E: synthetic Oracle -> WARNING v2 -> derived search/relations.

No DB session, Catalog import, activation, live Oracle/DEMIS, LLM or network.
An unsaved WARNING CatalogImportRevision below is test-only; it is never
eligible for activation and does not establish independent DBA preflight.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from app.models.catalog_import import CatalogImportRevision
from app.services.data_discovery_document import build_documents_for_revision
from app.services.data_discovery_search.relation import expand_relations
from tests.test_s06c_oracle_inspector_candidate_chain import SOURCE, _candidate, _inspect


def _in_memory_warning_revision(snapshot, *, revision_id: int = 101):
    archive, validation = _candidate(snapshot)
    assert archive
    assert validation.package_readiness == "WARNING"
    assert validation.activation_eligible is False
    parsed = validation.parsed_documents
    # Not added to a Session. Intentionally keep WARNING rather than fabricate
    # a READY revision or touch the active Catalog pointer.
    revision = CatalogImportRevision(
        id=revision_id,
        source_name=SOURCE,
        schema_fingerprint=validation.schema_fingerprint,
        package_readiness="WARNING",
        tables_json=parsed["tables.json"],
        columns_json=parsed["columns.json"],
        relations_json=parsed["relations.json"],
        indexes_json=parsed["indexes.json"],
        categories_json=parsed["categories.json"],
    )
    return revision, build_documents_for_revision(revision)


def _by_key(documents):
    result = {doc.document_key: doc for doc in documents}
    assert len(result) == len(documents), "Duplicate search-document physical keys"
    return result


def test_inspector_warning_package_yields_six_bound_metadata_documents():
    revision, documents = _in_memory_warning_revision(_inspect())
    by_key = _by_key(documents)
    expected = {
        "TABLE:DEMIS_OWNER.TB_PATIENT",
        "TABLE:DEMIS_OWNER.TB_VISIT",
        "COLUMN:DEMIS_OWNER.TB_PATIENT.PATIENT_ID",
        "COLUMN:DEMIS_OWNER.TB_PATIENT.SITE_ID",
        "COLUMN:DEMIS_OWNER.TB_VISIT.PATIENT_ID",
        "COLUMN:DEMIS_OWNER.TB_VISIT.SITE_ID",
    }
    assert set(by_key) == expected
    assert all(
        (doc.source_name, doc.catalog_revision_id, doc.schema_fingerprint)
        == (SOURCE, revision.id, revision.schema_fingerprint)
        for doc in documents
    )

    visit = by_key["TABLE:DEMIS_OWNER.TB_VISIT"]
    assert "IX_VISIT_PATIENT" in visit.searchable_text
    assert "FK_VISIT_PATIENT" in visit.searchable_text
    assert "PATIENT_ID->PATIENT_ID, SITE_ID->SITE_ID" in visit.searchable_text
    assert revision.package_readiness == "WARNING"


def test_actual_candidate_composite_fk_expands_outbound_and_inbound():
    revision, _ = _in_memory_warning_revision(_inspect())
    outgoing = expand_relations(
        revision, seed_tables=[("DEMIS_OWNER", "TB_VISIT")], max_hops=1,
    )
    assert [(item.schema_name, item.table_name, item.hop_distance)
            for item in outgoing] == [("DEMIS_OWNER", "TB_PATIENT", 1)]
    hop = outgoing[0].path[0]
    assert (hop.constraint_name, hop.direction) == ("FK_VISIT_PATIENT", "outbound")
    assert hop.from_columns == ("PATIENT_ID", "SITE_ID")
    assert hop.to_columns == ("PATIENT_ID", "SITE_ID")

    incoming = expand_relations(
        revision, seed_tables=[("DEMIS_OWNER", "TB_PATIENT")], max_hops=1,
    )
    assert [(item.schema_name, item.table_name, item.hop_distance)
            for item in incoming] == [("DEMIS_OWNER", "TB_VISIT", 1)]
    inverse = incoming[0].path[0]
    assert inverse.direction == "inbound"
    assert inverse.from_columns == ("PATIENT_ID", "SITE_ID")
    assert inverse.to_columns == ("PATIENT_ID", "SITE_ID")


def test_comment_drift_updates_affected_document_fingerprints_only():
    previous, before_docs = _in_memory_warning_revision(_inspect("rich"), revision_id=101)
    current, after_docs = _in_memory_warning_revision(
        _inspect("changed_comment"), revision_id=102,
    )
    assert previous.schema_fingerprint != current.schema_fingerprint

    old, new = _by_key(before_docs), _by_key(after_docs)
    assert set(old) == set(new)
    changed = {key for key in old
               if old[key].document_fingerprint != new[key].document_fingerprint}
    assert changed == {
        "TABLE:DEMIS_OWNER.TB_PATIENT",
        "TABLE:DEMIS_OWNER.TB_VISIT",
        "COLUMN:DEMIS_OWNER.TB_PATIENT.PATIENT_ID",
        "COLUMN:DEMIS_OWNER.TB_VISIT.PATIENT_ID",
        "COLUMN:DEMIS_OWNER.TB_VISIT.SITE_ID",
    }
    unchanged = "COLUMN:DEMIS_OWNER.TB_PATIENT.SITE_ID"
    assert old[unchanged].document_fingerprint == new[unchanged].document_fingerprint
    assert old[unchanged].source_fingerprint == new[unchanged].source_fingerprint
    # Even unchanged local text belongs to a different overall Catalog
    # fingerprint; this metadata is not a permission or activation pointer.
    assert old[unchanged].schema_fingerprint != new[unchanged].schema_fingerprint


def test_dictionary_row_order_does_not_rewrite_derived_document_fingerprints():
    _, docs_a = _in_memory_warning_revision(_inspect(), revision_id=101)
    _, docs_b = _in_memory_warning_revision(
        _inspect(reversed_rows=True), revision_id=102,
    )
    before, after = _by_key(docs_a), _by_key(docs_b)
    assert set(before) == set(after)
    assert {
        key: (doc.source_fingerprint, doc.document_fingerprint, doc.searchable_text)
        for key, doc in before.items()
    } == {
        key: (doc.source_fingerprint, doc.document_fingerprint, doc.searchable_text)
        for key, doc in after.items()
    }


def test_sensitive_dictionary_expressions_cannot_enter_search_documents():
    baseline = _inspect()
    noisy = deepcopy(baseline)
    noisy.columns[0] = replace(
        noisy.columns[0], default_value="S06E_SENSITIVE_DEFAULT_SQL",
    )
    noisy.indexes[0] = replace(
        noisy.indexes[0], index_definition="S06E_SENSITIVE_INDEX_SQL",
    )
    first_rev, first_docs = _in_memory_warning_revision(baseline)
    second_rev, second_docs = _in_memory_warning_revision(noisy)
    assert first_rev.schema_fingerprint == second_rev.schema_fingerprint
    first, second = _by_key(first_docs), _by_key(second_docs)
    assert {
        key: (doc.searchable_text, doc.document_fingerprint, doc.source_fingerprint)
        for key, doc in first.items()
    } == {
        key: (doc.searchable_text, doc.document_fingerprint, doc.source_fingerprint)
        for key, doc in second.items()
    }
    assert "S06E_SENSITIVE" not in " ".join(
        doc.searchable_text for doc in second_docs
    )
