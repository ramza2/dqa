"""Phase 29-B: Structured Query Plan contract and validation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domain.semantic_resource import MAPPING_FORMAT_VERSION, FieldCapability
from app.domain.structured_query_plan import (
    MAX_FILTERS,
    MAX_SELECT_FIELDS,
    PLAN_FORMAT_VERSION,
    PlanIssueCode,
    PlanValidationStatus,
)
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
from app.services.semantic_resource import SemanticResourceRegistry
from app.services.structured_query_plan import validate_structured_query_plan

pytestmark = pytest.mark.integration

SOURCE = "oracle_demis_mock"
FINGERPRINT = "fp-plan-a"


def _catalog_docs() -> dict[str, Any]:
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
                "table_key": "DEMIS_OWNER.TB_WARD",
                "column_name": "WARD_CD",
                "data_type": "VARCHAR2",
                "primary_key": True,
            },
        ],
        "relations": [
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
        ],
    }


def _seed_active(
    session: Session,
    *,
    source_name: str = SOURCE,
    fingerprint: str = FINGERPRINT,
    archive_sha256: str = "d" * 64,
) -> CatalogImportRevision:
    docs = _catalog_docs()
    revision = CatalogImportRevision(
        source_name=source_name,
        db_type="oracle",
        database_name="FREEPDB1",
        default_schema="DEMIS_OWNER",
        package_format="demis-catalog-package",
        package_version="2.0",
        package_readiness="READY",
        schema_fingerprint=fingerprint,
        archive_sha256=archive_sha256,
        manifest_sha256="e" * 64,
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


def _mapping(revision_id: int, *, fingerprint: str = FINGERPRINT) -> SemanticMappingDocument:
    return SemanticMappingDocument(
        mapping_format_version=MAPPING_FORMAT_VERSION,
        mapping_version="plan-test-1",
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
                ],
                relationships=[
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
                                    source_column="WARD_CD",
                                    target_column="WARD_CD",
                                )
                            ],
                        ),
                    )
                ],
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


def _registry(session: Session, **kwargs: Any) -> tuple[CatalogImportRevision, SemanticResourceRegistry]:
    rev = _seed_active(session, **kwargs)
    return rev, SemanticResourceRegistry.from_mapping(_mapping(rev.id, fingerprint=kwargs.get("fingerprint", FINGERPRINT)))


def _issue_codes(result) -> set[str]:
    return {str(i.code) for i in result.issues}


def test_valid_select_filter_sort_plan(db_session: Session) -> None:
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
        sort=[PlanSortSpec(field_key="ward_code", direction="DESC")],
        limit=50,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.VALID
    assert result.validation_only is True
    assert result.executable is False
    assert result.approved is False
    assert result.catalog_revision_id == rev.id
    assert result.schema_fingerprint == FINGERPRINT
    assert result.mapping_version == "plan-test-1"
    assert [f.field_key for f in result.select] == ["admission_id", "ward_code"]
    assert result.filters[0].value == 42
    assert result.sort[0].direction == "DESC"
    assert result.limit == 50
    assert result.issues == []


def test_allowed_grouping_aggregation_and_relationship(db_session: Session) -> None:
    _, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["ward_code"],
        group_by=["ward_code"],
        aggregations=[
            PlanAggregationSpec(function="COUNT", field_key="admission_id", alias="adm_count"),
            PlanAggregationSpec(function="SUM", field_key="admission_id"),
        ],
        relationships=["admission_ward"],
        limit=100,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.VALID
    assert result.relationships == ["admission_ward"]
    assert {a.function for a in result.aggregations} == {"COUNT", "SUM"}


def test_unknown_resource_field_relationship(db_session: Session) -> None:
    _, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.missing",
        select=["admission_id"],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.INVALID
    assert PlanIssueCode.UNKNOWN_RESOURCE in _issue_codes(result)

    plan2 = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["not_a_field"],
        filters=[PlanFilterPredicate(field_key="ghost", operator="EQ", value=1)],
        relationships=["no_such_rel"],
        limit=10,
    )
    result2 = validate_structured_query_plan(db_session, plan2, registry=registry)
    codes = _issue_codes(result2)
    assert PlanIssueCode.UNKNOWN_FIELD in codes
    assert PlanIssueCode.UNKNOWN_RELATIONSHIP in codes


def test_missing_capability_and_wrong_filter_type_operator(db_session: Session) -> None:
    _, registry = _registry(db_session)
    # admission_id lacks SORT
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        sort=[PlanSortSpec(field_key="admission_id", direction="ASC")],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.INVALID
    assert PlanIssueCode.MISSING_CAPABILITY in _issue_codes(result)

    # string field with LT (unsupported) + wrong value type on integer EQ
    plan2 = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["ward_code"],
        filters=[
            PlanFilterPredicate(field_key="ward_code", operator="LT", value="A"),
            PlanFilterPredicate(field_key="admission_id", operator="EQ", value="not-int"),
        ],
        limit=10,
    )
    result2 = validate_structured_query_plan(db_session, plan2, registry=registry)
    codes = _issue_codes(result2)
    assert PlanIssueCode.UNSUPPORTED_OPERATOR in codes
    assert PlanIssueCode.INVALID_FILTER_VALUE in codes


def test_stale_mapping_rejected(db_session: Session) -> None:
    rev = _seed_active(db_session)
    stale = _mapping(rev.id).model_copy(
        update={"catalog_revision_id": rev.id + 99, "schema_fingerprint": "fp-stale"}
    )
    registry = SemanticResourceRegistry.from_mapping(stale)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.STALE
    assert PlanIssueCode.STALE_MAPPING in _issue_codes(result)
    assert result.executable is False


def test_cross_source_mapping_rejected(db_session: Session) -> None:
    rev = _seed_active(db_session)
    forged = _mapping(rev.id).model_copy(update={"source_name": "oracle_demis_other"})
    # Inject under the plan's source key while document claims another source.
    registry = SemanticResourceRegistry(_by_source={SOURCE: forged})
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.INVALID
    assert PlanIssueCode.CROSS_SOURCE in _issue_codes(result)


def test_default_registry_not_configured(db_session: Session) -> None:
    _seed_active(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan)
    assert result.status == PlanValidationStatus.NOT_CONFIGURED
    assert PlanIssueCode.NOT_CONFIGURED in _issue_codes(result)
    assert result.approved is False


def test_sql_injection_shaped_inputs_rejected(db_session: Session) -> None:
    _, registry = _registry(db_session)
    with pytest.raises(ValidationError):
        StructuredQueryPlan.model_validate(
            {
                "source_name": SOURCE,
                "resource_key": "synthetic.admission",
                "select": ["admission_id"],
                "limit": 10,
                "sql": "SELECT * FROM dual",
            }
        )
    with pytest.raises(ValidationError):
        StructuredQueryPlan(
            source_name=SOURCE,
            resource_key="synthetic.admission",
            select=["admission_id;DROP"],
            limit=10,
        )
    with pytest.raises(ValidationError):
        PlanFilterPredicate(field_key="ward_code", operator="EQ OR 1=1", value="x")

    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["ward_code"],
        filters=[
            PlanFilterPredicate(
                field_key="ward_code",
                operator="EQ",
                value="W01'; DROP TABLE x--",
            )
        ],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.INVALID
    assert PlanIssueCode.FORBIDDEN_INPUT in _issue_codes(result)


def test_oversized_plans_rejected() -> None:
    with pytest.raises(ValidationError):
        StructuredQueryPlan(
            source_name=SOURCE,
            resource_key="synthetic.admission",
            select=[f"f{i}" for i in range(MAX_SELECT_FIELDS + 1)],
            limit=10,
        )
    with pytest.raises(ValidationError):
        StructuredQueryPlan(
            source_name=SOURCE,
            resource_key="synthetic.admission",
            select=["admission_id"],
            filters=[
                PlanFilterPredicate(field_key="admission_id", operator="EQ", value=i)
                for i in range(MAX_FILTERS + 1)
            ],
            limit=10,
        )
    with pytest.raises(ValidationError):
        StructuredQueryPlan(
            source_name=SOURCE,
            resource_key="synthetic.admission",
            select=["admission_id"],
            limit=1001,
        )


def test_validated_plan_is_immutable(db_session: Session) -> None:
    _, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.VALID
    with pytest.raises(ValidationError):
        result.executable = True  # type: ignore[misc]
    with pytest.raises(ValidationError):
        result.status = PlanValidationStatus.INVALID  # type: ignore[misc]


def test_unsupported_aggregation_on_string_field(db_session: Session) -> None:
    _, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["ward_code"],
        group_by=["ward_code"],
        aggregations=[PlanAggregationSpec(function="SUM", field_key="ward_code")],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.INVALID
    assert PlanIssueCode.UNSUPPORTED_AGGREGATION in _issue_codes(result)


def test_null_and_in_list_handling(db_session: Session) -> None:
    _, registry = _registry(db_session)
    plan = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        filters=[
            PlanFilterPredicate(field_key="ward_code", operator="IS_NULL", value=None),
            PlanFilterPredicate(
                field_key="admission_id", operator="IN", value=[1, 2, 3]
            ),
        ],
        limit=10,
    )
    result = validate_structured_query_plan(db_session, plan, registry=registry)
    assert result.status == PlanValidationStatus.VALID

    bad = StructuredQueryPlan(
        source_name=SOURCE,
        resource_key="synthetic.admission",
        select=["admission_id"],
        filters=[
            PlanFilterPredicate(field_key="ward_code", operator="IS_NULL", value="x"),
            PlanFilterPredicate(field_key="admission_id", operator="IN", value=[]),
        ],
        limit=10,
    )
    result_bad = validate_structured_query_plan(db_session, bad, registry=registry)
    assert result_bad.status == PlanValidationStatus.INVALID
    assert PlanIssueCode.INVALID_FILTER_VALUE in _issue_codes(result_bad)
