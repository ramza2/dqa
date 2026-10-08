"""Phase 29-A: Semantic Resource contracts, validation, and registry tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domain.data_discovery import DiscoveryIdentityKind
from app.domain.semantic_resource import (
    MAPPING_FORMAT_VERSION,
    FieldCapability,
    LogicalDiscoveryIdentity,
    SemanticIssueCode,
    SemanticMappingStatus,
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
from app.services.catalog_active import activate_catalog_revision
from app.services.semantic_resource import (
    SemanticResourceRegistry,
    get_default_semantic_registry,
    resolve_semantic_resources,
    validate_semantic_mapping,
)
from app.services.catalog_query import resolve_active_revision

pytestmark = pytest.mark.integration

SOURCE = "oracle_demis_mock"
FINGERPRINT = "fp-semantic-a"


def _catalog_docs() -> dict[str, Any]:
    """Synthetic Oracle-mock Catalog shapes (not real DEMIS clinical mappings)."""
    tables = [
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_ADM_HIST",
            "table_comment": "synthetic admission history",
        },
        {
            "table_key": "DEMIS_OWNER.TB_WARD",
            "schema_name": "DEMIS_OWNER",
            "table_name": "TB_WARD",
            "table_comment": "synthetic ward master",
        },
        {
            "table_key": "OTHER_OWNER.TB_ADM_HIST",
            "schema_name": "OTHER_OWNER",
            "table_name": "TB_ADM_HIST",
            "table_comment": "same table name other schema",
        },
    ]
    columns = [
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "column_name": "ADM_ID",
            "data_type": "NUMBER",
            "primary_key": True,
            "column_comment": "synthetic admission id",
        },
        {
            "table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "column_name": "WARD_CD",
            "data_type": "VARCHAR2",
            "column_comment": "synthetic ward code",
        },
        {
            "table_key": "DEMIS_OWNER.TB_WARD",
            "column_name": "WARD_CD",
            "data_type": "VARCHAR2",
            "primary_key": True,
            "column_comment": "ward pk",
        },
        {
            "table_key": "OTHER_OWNER.TB_ADM_HIST",
            "column_name": "ADM_ID",
            "data_type": "NUMBER",
            "primary_key": True,
        },
    ]
    relations = [
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
        },
        # Duplicate-shaped FK for ambiguity tests (same keys, second copy).
        {
            "constraint_name": "FK_DUP_AMBIG",
            "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "target_table_key": "DEMIS_OWNER.TB_WARD",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "WARD_CD",
                    "target_column": "WARD_CD",
                }
            ],
        },
        {
            "constraint_name": "FK_DUP_AMBIG",
            "source_table_key": "DEMIS_OWNER.TB_ADM_HIST",
            "target_table_key": "DEMIS_OWNER.TB_WARD",
            "column_mapping": [
                {
                    "ordinal_position": 1,
                    "source_column": "WARD_CD",
                    "target_column": "WARD_CD",
                }
            ],
        },
    ]
    return {
        "tables": tables,
        "columns": columns,
        "relations": relations,
    }


def _make_revision(
    session: Session,
    *,
    source_name: str = SOURCE,
    fingerprint: str = FINGERPRINT,
    archive_sha256: str = "a" * 64,
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
        manifest_sha256="b" * 64,
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
    return revision


def _seed_active(session: Session, **kwargs: Any) -> CatalogImportRevision:
    rev = _make_revision(session, **kwargs)
    activate_catalog_revision(session, rev.id)
    session.flush()
    return rev


def _valid_mapping(revision_id: int, *, fingerprint: str = FINGERPRINT) -> SemanticMappingDocument:
    return SemanticMappingDocument(
        mapping_format_version=MAPPING_FORMAT_VERSION,
        mapping_version="test-1",
        source_name=SOURCE,
        catalog_revision_id=revision_id,
        schema_fingerprint=fingerprint,
        provenance=MappingProvenance(author="pytest", review_status="TEST_ONLY"),
        resources=[
            LogicalResourceDefinition(
                resource_key="synthetic.admission",
                description="Synthetic admission resource for tests",
                physical_table=PhysicalTableRef(
                    schema_name="DEMIS_OWNER", table_name="TB_ADM_HIST"
                ),
                fields=[
                    LogicalFieldDefinition(
                        field_key="admission_id",
                        description="Synthetic id field",
                        data_type="integer",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="ADM_ID",
                        ),
                        capabilities=[FieldCapability.SELECT, FieldCapability.FILTER],
                    ),
                    LogicalFieldDefinition(
                        field_key="ward_code",
                        data_type="string",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="WARD_CD",
                        ),
                        capabilities=["SELECT", "FILTER", "SORT"],
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


def _issue_codes(result) -> set[str]:
    return {str(i.code) for i in result.issues}


def test_default_registry_is_not_configured(db_session: Session) -> None:
    _seed_active(db_session)
    result = resolve_semantic_resources(db_session, SOURCE)
    assert result.status == SemanticMappingStatus.NOT_CONFIGURED
    assert SemanticIssueCode.NOT_CONFIGURED in _issue_codes(result)
    assert result.resources == []
    assert get_default_semantic_registry().configured_sources() == frozenset()


def test_valid_synthetic_mapping_against_oracle_mock_catalog(db_session: Session) -> None:
    rev = _seed_active(db_session)
    mapping = _valid_mapping(rev.id)
    registry = SemanticResourceRegistry.from_mapping(mapping)

    result = resolve_semantic_resources(db_session, SOURCE, registry=registry)

    assert result.status == SemanticMappingStatus.VALID
    assert result.catalog_revision_id == rev.id
    assert result.schema_fingerprint == FINGERPRINT
    assert result.mapping_version == "test-1"
    assert {r.resource_key for r in result.resources} == {
        "synthetic.admission",
        "synthetic.ward",
    }
    admission = next(r for r in result.resources if r.resource_key == "synthetic.admission")
    assert admission.fields[0].catalog_data_type == "NUMBER"
    assert "FILTER" in admission.fields[0].capabilities
    assert len(admission.relationships) == 1
    assert result.issues == []


def test_missing_table_column_and_fk(db_session: Session) -> None:
    rev = _seed_active(db_session)
    mapping = SemanticMappingDocument(
        mapping_version="bad-1",
        source_name=SOURCE,
        catalog_revision_id=rev.id,
        schema_fingerprint=FINGERPRINT,
        resources=[
            LogicalResourceDefinition(
                resource_key="synthetic.missing",
                physical_table=PhysicalTableRef(
                    schema_name="DEMIS_OWNER", table_name="TB_DOES_NOT_EXIST"
                ),
                fields=[
                    LogicalFieldDefinition(
                        field_key="x",
                        data_type="string",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_DOES_NOT_EXIST",
                            column_name="NOPE",
                        ),
                        capabilities=[FieldCapability.SELECT],
                    )
                ],
                relationships=[
                    LogicalRelationshipDefinition(
                        relationship_key="missing_fk",
                        from_resource_key="synthetic.missing",
                        to_resource_key="synthetic.missing",
                        catalog_fk=CatalogFkBinding(
                            constraint_name="FK_NOT_REAL",
                            source_schema_name="DEMIS_OWNER",
                            source_table_name="TB_DOES_NOT_EXIST",
                            target_schema_name="DEMIS_OWNER",
                            target_table_name="TB_WARD",
                            column_mappings=[
                                CatalogFkColumnBinding(
                                    source_column="X", target_column="WARD_CD"
                                )
                            ],
                        ),
                    )
                ],
            )
        ],
    )
    result = resolve_semantic_resources(
        db_session, SOURCE, registry=SemanticResourceRegistry.from_mapping(mapping)
    )
    assert result.status == SemanticMappingStatus.INVALID
    codes = _issue_codes(result)
    assert SemanticIssueCode.MISSING_TABLE in codes
    assert SemanticIssueCode.MISSING_COLUMN in codes
    assert SemanticIssueCode.MISSING_FK in codes


def test_ambiguous_fk_rejected(db_session: Session) -> None:
    rev = _seed_active(db_session)
    mapping = _valid_mapping(rev.id)
    admission = mapping.resources[0].model_copy(
        update={
            "relationships": [
                LogicalRelationshipDefinition(
                    relationship_key="ambiguous_ward",
                    from_resource_key="synthetic.admission",
                    to_resource_key="synthetic.ward",
                    catalog_fk=CatalogFkBinding(
                        constraint_name="FK_DUP_AMBIG",
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
        }
    )
    mapping = mapping.model_copy(update={"resources": [admission, mapping.resources[1]]})
    result = validate_semantic_mapping(mapping, resolve_active_revision(db_session, SOURCE))
    assert result.status == SemanticMappingStatus.INVALID
    assert SemanticIssueCode.AMBIGUOUS_FK in _issue_codes(result)


def test_cross_source_rejected(db_session: Session) -> None:
    rev = _seed_active(db_session)
    mapping = _valid_mapping(rev.id)
    forged = mapping.model_copy(update={"source_name": "oracle_demis_other"})
    active = resolve_active_revision(db_session, SOURCE)
    result = validate_semantic_mapping(forged, active)
    assert result.status == SemanticMappingStatus.INVALID
    assert SemanticIssueCode.CROSS_SOURCE in _issue_codes(result)


def test_stale_revision_and_fingerprint(db_session: Session) -> None:
    rev = _seed_active(db_session)
    mapping = _valid_mapping(rev.id).model_copy(
        update={"catalog_revision_id": rev.id + 999, "schema_fingerprint": "fp-stale"}
    )
    result = resolve_semantic_resources(
        db_session, SOURCE, registry=SemanticResourceRegistry.from_mapping(mapping)
    )
    assert result.status == SemanticMappingStatus.STALE
    codes = _issue_codes(result)
    assert SemanticIssueCode.STALE_REVISION in codes
    assert SemanticIssueCode.STALE_FINGERPRINT in codes
    assert result.resources == []


def test_duplicate_logical_keys(db_session: Session) -> None:
    rev = _seed_active(db_session)
    base = _valid_mapping(rev.id)
    dup_resource = base.resources[0].model_copy()
    mapping = base.model_copy(
        update={
            "resources": [
                base.resources[0],
                dup_resource,
                base.resources[1],
            ]
        }
    )
    # Also duplicate field keys inside first resource.
    fields = list(mapping.resources[0].fields) + [mapping.resources[0].fields[0]]
    mapping.resources[0] = mapping.resources[0].model_copy(update={"fields": fields})

    result = validate_semantic_mapping(mapping, resolve_active_revision(db_session, SOURCE))
    assert result.status == SemanticMappingStatus.INVALID
    codes = _issue_codes(result)
    assert SemanticIssueCode.DUPLICATE_RESOURCE_KEY in codes
    assert SemanticIssueCode.DUPLICATE_FIELD_KEY in codes


def test_unsupported_field_capabilities_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        LogicalFieldDefinition(
            field_key="bad",
            data_type="string",
            physical_column=PhysicalColumnRef(
                schema_name="DEMIS_OWNER",
                table_name="TB_ADM_HIST",
                column_name="ADM_ID",
            ),
            capabilities=["SELECT", "JOIN"],  # type: ignore[list-item]
        )


def test_unsupported_capability_rejected_by_validator(db_session: Session) -> None:
    rev = _seed_active(db_session)
    field_def = LogicalFieldDefinition.model_construct(
        field_key="bad_cap",
        description=None,
        data_type="string",
        physical_column=PhysicalColumnRef(
            schema_name="DEMIS_OWNER",
            table_name="TB_ADM_HIST",
            column_name="ADM_ID",
        ),
        capabilities=["SELECT", "EXECUTE_SQL"],
    )
    resource = LogicalResourceDefinition.model_construct(
        resource_key="synthetic.caps",
        description=None,
        physical_table=PhysicalTableRef(
            schema_name="DEMIS_OWNER", table_name="TB_ADM_HIST"
        ),
        fields=[field_def],
        relationships=[],
    )
    mapping = SemanticMappingDocument.model_construct(
        mapping_format_version=MAPPING_FORMAT_VERSION,
        mapping_version="caps-1",
        source_name=SOURCE,
        catalog_revision_id=rev.id,
        schema_fingerprint=FINGERPRINT,
        provenance=MappingProvenance(review_status="TEST_ONLY"),
        resources=[resource],
    )
    result = validate_semantic_mapping(mapping, resolve_active_revision(db_session, SOURCE))
    assert result.status == SemanticMappingStatus.INVALID
    assert SemanticIssueCode.UNKNOWN_CAPABILITY in _issue_codes(result)


def test_missing_column_on_existing_table(db_session: Session) -> None:
    rev = _seed_active(db_session)
    mapping = SemanticMappingDocument(
        mapping_version="col-miss",
        source_name=SOURCE,
        catalog_revision_id=rev.id,
        schema_fingerprint=FINGERPRINT,
        resources=[
            LogicalResourceDefinition(
                resource_key="synthetic.admission",
                physical_table=PhysicalTableRef(
                    schema_name="DEMIS_OWNER", table_name="TB_ADM_HIST"
                ),
                fields=[
                    LogicalFieldDefinition(
                        field_key="ghost",
                        data_type="string",
                        physical_column=PhysicalColumnRef(
                            schema_name="DEMIS_OWNER",
                            table_name="TB_ADM_HIST",
                            column_name="NOT_A_COLUMN",
                        ),
                        capabilities=[FieldCapability.SELECT],
                    )
                ],
            )
        ],
    )
    result = validate_semantic_mapping(mapping, resolve_active_revision(db_session, SOURCE))
    assert result.status == SemanticMappingStatus.INVALID
    assert SemanticIssueCode.MISSING_COLUMN in _issue_codes(result)


def test_logical_discovery_identity_requires_logical_kind() -> None:
    identity = LogicalDiscoveryIdentity(
        identity_kind=DiscoveryIdentityKind.LOGICAL,
        source_name=SOURCE,
        catalog_revision_id=1,
        schema_fingerprint=FINGERPRINT,
        resource_key="synthetic.admission",
        field_key="admission_id",
    )
    assert identity.identity_kind is DiscoveryIdentityKind.LOGICAL
    with pytest.raises(ValueError):
        LogicalDiscoveryIdentity(
            identity_kind=DiscoveryIdentityKind.PHYSICAL,
            source_name=SOURCE,
            catalog_revision_id=1,
            schema_fingerprint=FINGERPRINT,
            resource_key="synthetic.admission",
        )


def test_no_hardcoded_patient_encounter_in_default_registry() -> None:
    registry = get_default_semantic_registry()
    assert registry.configured_sources() == frozenset()
    # Guard: production module must not ship real clinical resource keys.
    import app.services.semantic_resource as mod
    import inspect

    source = inspect.getsource(mod)
    assert "Patient" not in source
    assert "Encounter" not in source
