"""S-06-B offline cross-schema/composite-FK Gold paths; no DB/Oracle.

Synthetic physical metadata only. A reference to a table in another schema
does not grant permissions or prove the actual Oracle object is visible.
"""
from __future__ import annotations

from app.models.catalog_import import CatalogImportRevision
from app.services.data_discovery_search.relation import expand_relations


def _edge(name, source, target, mappings):
    return {
        "constraint_name": name,
        "source_table_key": source,
        "target_table_key": target,
        "column_mapping": [
            {"ordinal_position": position, "source_column": from_col,
             "target_column": to_col}
            for position, from_col, to_col in mappings
        ],
    }


def _graph():
    # Composite FK has deliberately shuffled wire order. DB/column identity
    # must come from ordinal_position, not input-array order.
    return CatalogImportRevision(relations_json={"relations": [
        _edge(
            "FK_CLINICAL_LAB", "DEMIS_OWNER.TB_CLINICAL", "DEMIS_OWNER.TB_LAB",
            [(2, "VISIT_ID", "VISIT_ID"), (1, "LAB_ID", "LAB_ID")],
        ),
        _edge(
            "FK_LAB_REPORT", "DEMIS_OWNER.TB_LAB", "REF_OWNER.TB_REPORT",
            [(1, "REPORT_ID", "ID")],
        ),
        _edge(
            "FK_REPORT_CLINICAL", "REF_OWNER.TB_REPORT",
            "DEMIS_OWNER.TB_CLINICAL", [(1, "CLINICAL_ID", "ID")],
        ),
        # Same bare names in a completely separate subgraph.
        _edge(
            "FK_OTHER_CLINICAL_LAB", "OTHER_OWNER.TB_CLINICAL",
            "OTHER_OWNER.TB_LAB", [(1, "LAB_ID", "LAB_ID")],
        ),
    ]})


def test_gold_composite_fk_ordinal_mapping_and_exact_one_hop():
    graph = _graph()
    direct = expand_relations(
        graph, seed_tables=[("DEMIS_OWNER", "TB_CLINICAL")], max_hops=1,
    )
    expected = {
        ("DEMIS_OWNER", "TB_LAB"),
        ("REF_OWNER", "TB_REPORT"),  # inverse of FK_REPORT_CLINICAL
    }
    assert {(x.schema_name, x.table_name) for x in direct} == expected
    lab = next(x for x in direct if x.table_name == "TB_LAB")
    assert lab.hop_distance == 1
    assert len(lab.path) == 1
    hop = lab.path[0]
    assert hop.constraint_name == "FK_CLINICAL_LAB"
    assert hop.direction == "outbound"
    assert hop.from_columns == ("LAB_ID", "VISIT_ID")
    assert hop.to_columns == ("LAB_ID", "VISIT_ID")


def test_gold_reverse_composite_fk_preserves_column_pairing():
    related = expand_relations(
        _graph(), seed_tables=[("DEMIS_OWNER", "TB_LAB")], max_hops=1,
    )
    clinical = next(x for x in related if (x.schema_name, x.table_name)
                    == ("DEMIS_OWNER", "TB_CLINICAL"))
    assert clinical.path[0].constraint_name == "FK_CLINICAL_LAB"
    assert clinical.path[0].direction == "inbound"
    assert clinical.path[0].from_columns == ("LAB_ID", "VISIT_ID")
    assert clinical.path[0].to_columns == ("LAB_ID", "VISIT_ID")


def test_gold_multihop_cycle_and_same_name_other_schema_not_leaked():
    related = expand_relations(
        _graph(), seed_tables=[("DEMIS_OWNER", "TB_CLINICAL")], max_hops=3,
    )
    keys = [(x.schema_name, x.table_name) for x in related]
    assert set(keys) == {
        ("DEMIS_OWNER", "TB_LAB"),
        ("REF_OWNER", "TB_REPORT"),
    }
    assert len(keys) == len(set(keys))
    assert ("DEMIS_OWNER", "TB_CLINICAL") not in keys
    assert all(x.hop_distance == 1 for x in related)
    assert all(x.hop_distance <= 3 for x in related)
    # A reference-only schema is not the same as a clinical authorization.
    assert any(x.schema_name == "REF_OWNER" for x in related)
    assert not any(x.schema_name == "OTHER_OWNER" for x in related)

    # The disjoint same-named entity has a different, isolated traversal.
    other = expand_relations(
        _graph(), seed_tables=[("OTHER_OWNER", "TB_CLINICAL")], max_hops=3,
    )
    assert [(x.schema_name, x.table_name) for x in other] == [
        ("OTHER_OWNER", "TB_LAB")
    ]


def test_gold_missing_or_empty_seed_never_leaks_graph():
    assert expand_relations(_graph(), seed_tables=[], max_hops=3) == []
    assert expand_relations(
        _graph(), seed_tables=[("DEMIS_OWNER", "TB_CLINICAL")], max_hops=0,
    ) == []
    assert expand_relations(
        _graph(), seed_tables=[("UNKNOWN", "TB_CLINICAL")], max_hops=3,
    ) == []
