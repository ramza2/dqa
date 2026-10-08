"""Phase 29-C: Deterministic Oracle SELECT compiler tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.domain.query_compiler import CompilerIssueCode, CompilerStatus
from app.domain.semantic_resource import MAPPING_FORMAT_VERSION, FieldCapability
from app.domain.structured_query_plan import PLAN_FORMAT_VERSION
from app.models.catalog_import import CatalogImportRevision
from app.schemas.semantic_resource import (
    CatalogFkBinding,
    CatalogFkColumnBinding,
    LogicalFieldDefinition,
    LogicalRelationshipDefinition,
    LogicalResourceDefinition,
    MappingProvenance,
    PhysicalColumnRef,
    PhysicalTableRef,
    SemanticMappingDocument,
)
from app.schemas.structured_query_plan import (
    PlanAggregationSpec,
    PlanFilterPredicate,
    PlanSortSpec,
    StructuredQueryPlan,
)
from app.services.catalog_active import activate_catalog_revision
from app.services.query_compiler import compile_structured_query_plan
from app.services.semantic_resource import SemanticResourceRegistry

pytestmark = pytest.mark.integration

SOURCE = "oracle_demis_mock"
FINGERPRINT = "fp-compiler-a"


def _catalog_docs(*, composite_fk: bool = False) -> dict[str, Any]:
    relations: list[dict[str, Any]] = [
        {
            "constraint_name": "FK_ADM_WARD",
            "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "target_table_key": "DEMIS_OWNER.TB_WARD",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "WARD_CD",
                    "target_column": "WARD_CD",
                }
            ],
        }
    ]
    if composite_fk:
        relations.append(
            {
                "constraint_name": "FK_ADM_WARD_COMPOSITE",
                "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "target_table_key": "DEMIS_OWNER.TB_WARD",
                "column_mapping": [
                    {
                        "ordinal_position": 1,
                        "source_column": "WARD_CD",
                        "target_column": "WARD_CD",
                    },
                    {
                        "ordinal_position": 2,
                        "source_column": "HOSP_CD",
                        "target_column": "HOSP_CD",
                    },
                ],
            }
        )
    return {
        "tables": [
            {
                "table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "schema_name": "DEMIS_OWNER",
                "table_name": "TB_ADM_HIST",
            },
            {
                "table_key": "DEMIS_OWNER.TB_WARD",
                "schema_name": "DEMIS_OWNER",
                "table_name": "TB_WARD",
            },
        ],
        "columns": [
            {
                "table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "column_name": "ADM_ID",
                "data_type": "NUMBER",
                "primary_key": True,
            },
            {
                "table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "column_name": "WARD_CD",
                "data_type": "VARCHAR2",
            },
            {
                "table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "column_name": "HOSP_CD",
                "data_type": "VARCHAR2",
            },
            {
                "table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "column_name": "SCORE",
                "data_type": "NUMBER",
            },
            {
                "table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "column_name": "ADM_DT",
                "data_type": "DATE",
            },
            {
                "table_key": "DEMIS_OWNER.TB_ADM_HIST",
                "column_name": "ADM_TS",
                "data_type": "TIMESTAMP",
            },
            {
                "table_key": "DEMIS_OWNER.TB_WARD",
                "column_name": "WARD_CD",
                "data_type": "VARCHAR2",
                "primary_key": True,
            },
            {
                "table_key": "DEMIS_OWNER.TB_WARD",
                "column_name": "HOSP_CD",
                "data_type": "VARCHAR2",
            },
        ],
        "relations": relations,
    }


def _seed_active(
    session: Session,
    *,
    fingerprint: str = FINGERPRINT,
    archive_sha256: str = "f" * 64,
    composite_fk: bool = False,
) -> CatalogImportRevision:
    docs = _catalog_docs(composite_fk=composite_fk)
    revision = CatalogImportRevision(
        source_name=SOURCE,
        db_type="oracle",
        database_name="FREEPDB1",
        default_schema="DEMIS_OWNER",
        package_format="demis-catalog-package",
        package_version="2.0",
        package_readiness="READY",
        schema_fingerprint=fingerprint,
        archive_sha256=archive_sha256,
        manifest_sha256="1" * 64,
        generated_at=datetime(2026, 10, 8, tzinfo=UTC),
        validation_status="VALID",
        table_count=len(docs["tables"]),
        column_count=len(docs["columns"]),
        relation_count=len(docs["relations"]),
        index_count=0,
        category_count=0,
        category_assignment_count=0,
        managed_file_count=1,
        manifest_json={},
        database_json={},
        tables_json={"tables": docs["tables"]},
        columns_json={"columns": docs["columns"]},
        relations_json={"relations": docs["relations"]},
        indexes_json={"indexes": []},
        categories_json={"categories": [], "table_assignments": []},
        erd_json={},
        latest_run_json={},
        schema_snapshot_json={},
        preflight_json={},
        latest_diff_json={},
        managed_file_digests_json={},
    )
    session.add(revision)
    session.flush()
    session.refresh(revision)
    activate_catalog_revision(session, revision.id)
    session.flush()
    return revision


def _mapping(
    revision_id: int,
    *,
    fingerprint: str = FINGERPRINT,
    include_composite: bool = False,
) -> SemanticMappingDocument:
    relationships = [
        LogicalRelationshipDefinition(
            relationship_key="admission_ward",
            from_resource_key="synthetic.admission",
            to_resource_key="synthetic.ward",
            catalog_fk=CatalogFkBinding(
                constraint_name="FK_ADM_WARD",
                source_schema_name="DEMIS_OWNER",
                source_table_name="TB_ADM_HIST",
                target_schema_name="DEMIS_OWNER",
                target_table_name="TB_WARD",
                column_mappings=[
                    CatalogFkColumnBinding(
                        source_column="WARD_CD", target_column="WARD_CD"
                    )
                ],
            ),
        )
    ]
    if include_composite:
        relationships.append(
            LogicalRelationshipDefinition(
                relationship_key="admission_ward_composite",
                from_resource_key="synthetic.admission",
                to_resource_key="synthetic.ward",
                catalog_fk=CatalogFkBinding(
                    constraint_name="FK_ADM_WARD_COMPOSITE",
                    source_schema_name="DEMIS_OWNER",
                    source_table_name="TB_ADM_HIST",
                    target_schema_name="DEMIS_OWNER",
                    target_table_name="TB_WARD",
                    column_mappings=[
                        CatalogFkColumnBinding(
                            source_column="WARD_CD", target_column="WARD_CD"
                        ),
                        CatalogFkColumnBinding(
                            source_column="HOSP_CD", target_column="HOSP_CD"
                        ),
                    ],
                ),
            )
        )
    return SemanticMappingDocument(
        mapping_format_version=MAPPING_FORMAT_VERSION,
        mapping_version="compiler-test-1",
        source_name=SOURCE,
        catalog_revision_id=revision_id,
        schema_fingerprint=fingerprint,
        provenance=MappingProvenance(author="pytest", review_status="TEST_ONLY"),
        resources=[
            LogicalResourceDefinition(
                resource_key="synthetic.admission",
                physical_table=PhysicalTableRef(
                    schema_name="DEMIS_OWNER", table_name="TB_ADM_HIST"
                ),
                fields=[
                    LogicalFieldDefinition(
                        field_key="admission_id",
                        data_type="integer",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="ADM_ID",
                        ),
                        capabilities=[
                            FieldCapability.SELECT,
                            FieldCapability.FILTER,
                            FieldCapability.GROUP_BY,
                            FieldCapability.AGGREGATE,
                        ],
                    ),
                    LogicalFieldDefinition(
                        field_key="ward_code",
                        data_type="string",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="WARD_CD",
                        ),
                        capabilities=[
                            FieldCapability.SELECT,
                            FieldCapability.FILTER,
                            FieldCapability.SORT,
                            FieldCapability.GROUP_BY,
                            FieldCapability.AGGREGATE,
                        ],
                    ),
                    LogicalFieldDefinition(
                        field_key="hosp_code",
                        data_type="string",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="HOSP_CD",
                        ),
                        capabilities=[FieldCapability.SELECT, FieldCapability.FILTER],
                    ),
                    LogicalFieldDefinition(
                        field_key="score",
                        data_type="number",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="SCORE",
                        ),
                        capabilities=[
                            FieldCapability.SELECT,
                            FieldCapability.FILTER,
                            FieldCapability.AGGREGATE,
                        ],
                    ),
                    LogicalFieldDefinition(
                        field_key="adm_date",
                        data_type="date",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="ADM_DT",
                        ),
                        capabilities=[FieldCapability.SELECT, FieldCapability.FILTER],
                    ),
                    LogicalFieldDefinition(
                        field_key="adm_ts",
                        data_type="datetime",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="ADM_TS",
                        ),
                        capabilities=[FieldCapability.SELECT, FieldCapability.FILTER],
                    ),
                ],
                relationships=relationships,
            ),
            LogicalResourceDefinition(
                resource_key="synthetic.ward",
                physical_table=PhysicalTableRef(
                    schema_name="DEMIS_OWNER", table_name="TB_WARD"
                ),
                fields=[
                    LogicalFieldDefinition(
                        field_key="ward_code",
                        data_type="string",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_WARD",
                            column_name="WARD_CD",
                        ),
                        capabilities=[FieldCapability.SELECT],
                    )
                ],
            ),
        ],
    )


def _registry(
    session: Session,
    *,
    composite_fk: bool = False,
    fingerprint: str = FINGERPRINT,
) -> tuple[CatalogImportRevision, SemanticResourceRegistry]:
    rev = _seed_active(
        session, fingerprint=fingerprint, composite_fk=composite_fk, archive_sha256="a" * 64
    )
    return rev, SemanticResourceRegistry.from_mapping(
        _mapping(rev.id, fingerprint=fingerprint, include_composite=composite_fk)
    )


def _issue_codes(result) -> set[str]:
    return {str(i.code) for i in result.issues}


def test_oracle_select_with_typed_binds(db_session: Session) -> None:
    rev, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        plan_format_version=PLAN_FORMAT_VERSION,
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id", "ward_code"],
        filters=[
            PlanFilterPredicate(field_key="admission_id", operator="EQ", value=42),
            PlanFilterPredicate(field_key="ward_code", operator="EQ", value="W01"),
        ],
        sort=[PlanSortSpec(field_key="ward_code", direction="ASC")],
        limit=25,
    )
    result = compile_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == CompilerStatus.VALID
    assert result.preview_only is True
    assert result.executable is False
    assert result.approved is False
    assert result.catalog_revision_id == rev.id
    assert result.schema_fingerprint == FINGERPRINT
    assert result.mapping_version == "compiler-test-1"
    assert result.sql_text is not None
    assert "SELECT *" not in result.sql_text
    assert '"DEMIS_OWNER"."TB_ADM_HIST" t0' in result.sql_text
    assert "ROWNUM <= :p_limit" in result.sql_text
    assert ":p1" in result.sql_text and ":p2" in result.sql_text
    assert "42" not in result.sql_text
    assert "W01" not in result.sql_text
    assert result.bind_parameters == {"p1": 42, "p2": "W01", "p_limit": 25}
    assert result.sql_safety is not None and result.sql_safety.safe is True


def test_in_between_like_null_date_datetime_group_sort(db_session: Session) -> None:
    _, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["ward_code"],
        filters=[
            PlanFilterPredicate(field_key="admission_id", operator="IN", value=[1, 2]),
            PlanFilterPredicate(field_key="score", operator="BETWEEN", value=[0.5, 9.5]),
            PlanFilterPredicate(field_key="ward_code", operator="LIKE", value="W%"),
            PlanFilterPredicate(field_key="hosp_code", operator="IS_NULL", value=None),
            PlanFilterPredicate(field_key="adm_date", operator="EQ", value="2024-03-15"),
            PlanFilterPredicate(
                field_key="adm_ts", operator="EQ", value="2024-03-15T10:30:00"
            ),
        ],
        group_by=["ward_code"],
        aggregations=[
            PlanAggregationSpec(function="COUNT", field_key="admission_id", alias="adm_count"),
            PlanAggregationSpec(function="SUM", field_key="score", alias="score_sum"),
        ],
        sort=[PlanSortSpec(field_key="ward_code", direction="DESC")],
        limit=100,
    )
    result = compile_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == CompilerStatus.VALID
    sql = result.sql_text or ""
    assert "IN (:p1, :p2)" in sql
    assert "BETWEEN :p3 AND :p4" in sql
    assert "LIKE :p5" in sql
    assert 'IS NULL' in sql
    assert "GROUP BY t0.\"WARD_CD\"" in sql
    assert "COUNT(t0.\"ADM_ID\") AS \"adm_count\"" in sql
    assert "SUM(t0.\"SCORE\") AS \"score_sum\"" in sql
    assert "ORDER BY t0.\"WARD_CD\" DESC" in sql
    assert "2024-03-15" not in sql  # value bound, not inlined
    assert result.bind_parameters["p1"] == 1
    assert result.bind_parameters["p5"] == "W%"
    assert result.bind_parameters["p6"] == "2024-03-15"
    assert result.bind_parameters["p7"] == "2024-03-15T10:30:00"


def test_single_and_composite_fk_join(db_session: Session) -> None:
    _, registry = _registry(db_session, composite_fk=True)
    single = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        relationships=["admission_ward"],
        limit=10,
    )
    r1 = compile_structured_query_plan(db_session, single, registry=registry)
    assert r1.status == CompilerStatus.VALID
    assert 'INNER JOIN "DEMIS_OWNER"."TB_WARD" t1' in (r1.sql_text or "")
    assert 't0."WARD_CD" = t1."WARD_CD"' in (r1.sql_text or "")

    composite = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        relationships=["admission_ward_composite"],
        limit=10,
    )
    r2 = compile_structured_query_plan(db_session, composite, registry=registry)
    assert r2.status == CompilerStatus.VALID
    sql = r2.sql_text or ""
    assert 't0."WARD_CD" = t1."WARD_CD"' in sql
    assert 't0."HOSP_CD" = t1."HOSP_CD"' in sql


def test_ambiguous_join_rejected(db_session: Session) -> None:
    _, registry = _registry(db_session, composite_fk=True)
    # Both relationships target synthetic.ward — ambiguous if both selected.
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        relationships=["admission_ward", "admission_ward_composite"],
        limit=10,
    )
    result = compile_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == CompilerStatus.INVALID
    # Plan validation rejects ambiguous join before compile, or compiler does.
    assert _issue_codes(result) & {
        CompilerIssueCode.PLAN_INVALID,
        CompilerIssueCode.AMBIGUOUS_JOIN,
    }


def test_sql_injection_shaped_values_never_enter_sql(db_session: Session) -> None:
    _, registry = _registry(db_session)
    evil = "W01'; DROP TABLE x--"
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["ward_code"],
        filters=[PlanFilterPredicate(field_key="ward_code", operator="EQ", value=evil)],
        limit=10,
    )
    # 29-B rejects forbidden fragments before compile.
    result = compile_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == CompilerStatus.INVALID
    assert result.sql_text is None
    assert evil not in str(result.model_dump())


def test_default_registry_not_configured(db_session: Session) -> None:
    _seed_active(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        limit=10,
    )
    result = compile_structured_query_plan(db_session, plan)
    assert result.status == CompilerStatus.NOT_CONFIGURED
    assert CompilerIssueCode.NOT_CONFIGURED in _issue_codes(result)
    assert result.sql_text is None
    assert result.executable is False


def test_stale_mapping_rejected(db_session: Session) -> None:
    rev = _seed_active(db_session)
    stale = _mapping(rev.id).model_copy(
        update={"catalog_revision_id": rev.id + 9, "schema_fingerprint": "fp-stale"}
    )
    registry = SemanticResourceRegistry.from_mapping(stale)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        limit=10,
    )
    result = compile_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == CompilerStatus.STALE
    assert CompilerIssueCode.STALE_MAPPING in _issue_codes(result)
    assert result.sql_text is None


def test_deterministic_sql_and_bounded_limit(db_session: Session) -> None:
    _, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id", "ward_code"],
        filters=[
            PlanFilterPredicate(field_key="admission_id", operator="EQ", value=7),
            PlanFilterPredicate(field_key="ward_code", operator="IN", value=["A", "B"]),
        ],
        sort=[PlanSortSpec(field_key="ward_code", direction="ASC")],
        limit=50,
    )
    a = compile_structured_query_plan(db_session, plan, registry=registry)
    b = compile_structured_query_plan(db_session, plan, registry=registry)
    assert a.status == CompilerStatus.VALID
    assert a.sql_text == b.sql_text
    assert a.bind_parameters == b.bind_parameters
    assert a.bind_parameters["p_limit"] == 50
    assert "ROWNUM <= :p_limit" in (a.sql_text or "")


def test_unknown_relationship_and_invalid_plan(db_session: Session) -> None:
    _, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        relationships=["no_such_rel"],
        limit=10,
    )
    result = compile_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == CompilerStatus.INVALID
    assert result.sql_text is None
    assert CompilerIssueCode.PLAN_INVALID in _issue_codes(result)
