"""Semantic Resource mapping validation and read-only resolution (Phase 29-A).

Validates explicit mapping documents against one Active Catalog revision
snapshot. Does not infer clinical meaning, compile SQL, or persist approvals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryError
from app.domain.semantic_resource import (
    MAPPING_FORMAT_VERSION,
    SemanticIssueCode,
    SemanticMappingStatus,
    is_approved_capability,
)
from app.schemas.semantic_resource import (
    CatalogFkBinding,
    LogicalFieldDefinition,
    LogicalRelationshipDefinition,
    LogicalResourceDefinition,
    ResolvedLogicalField,
    ResolvedLogicalRelationship,
    ResolvedLogicalResource,
    SemanticMappingDocument,
    SemanticResolutionResult,
    SemanticValidationIssue,
)
from app.services.catalog_query import (
    ResolvedActiveRevision,
    _doc_list,
    _map_column,
    _map_relation,
    _map_table,
    resolve_active_revision,
)


@dataclass(frozen=True)
class _CatalogSnapshotIndex:
    """Indexed physical objects from one Active Catalog revision."""

    # (schema, table) -> mapped table items (len>1 => ambiguous)
    tables: dict[tuple[str, str], list[Any]]
    # (schema, table) -> column_name.casefold() -> mapped column items
    columns: dict[tuple[str, str], dict[str, list[Any]]]
    # FK match key -> mapped relations (len>1 => ambiguous)
    relations_by_key: dict[tuple[str, str, str, str, str], list[Any]]


@dataclass
class SemanticResourceRegistry:
    """Injectable read-only registry of explicit semantic mappings.

    Default runtime is empty (NOT_CONFIGURED). Tests inject synthetic documents.
    Arbitrary JSON is never treated as approved production authority.
    """

    _by_source: dict[str, SemanticMappingDocument] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> SemanticResourceRegistry:
        return cls()

    @classmethod
    def from_mapping(cls, mapping: SemanticMappingDocument) -> SemanticResourceRegistry:
        return cls(_by_source={mapping.source_name: mapping})

    @classmethod
    def from_mappings(
        cls, mappings: list[SemanticMappingDocument]
    ) -> SemanticResourceRegistry:
        by_source: dict[str, SemanticMappingDocument] = {}
        for mapping in mappings:
            if mapping.source_name in by_source:
                raise ValueError(
                    f"duplicate mapping for source_name={mapping.source_name!r}"
                )
            by_source[mapping.source_name] = mapping
        return cls(_by_source=by_source)

    def get_mapping(self, source_name: str) -> SemanticMappingDocument | None:
        return self._by_source.get(source_name)

    def configured_sources(self) -> frozenset[str]:
        return frozenset(self._by_source)


# Process-default registry: no trusted semantic mappings in normal runtime.
_DEFAULT_REGISTRY = SemanticResourceRegistry.empty()


def get_default_semantic_registry() -> SemanticResourceRegistry:
    """Return the empty default registry (no production clinical mappings)."""
    return _DEFAULT_REGISTRY


def resolve_semantic_resources(
    session: Session,
    source_name: str,
    *,
    registry: SemanticResourceRegistry | None = None,
) -> SemanticResolutionResult:
    """Resolve and validate semantic mappings for ``source_name``.

    Uses one Active Catalog revision snapshot via ``resolve_active_revision``.
    """
    reg = registry if registry is not None else get_default_semantic_registry()
    source = source_name.strip()
    if not source:
        return SemanticResolutionResult(
            status=SemanticMappingStatus.INVALID,
            source_name=source_name,
            issues=[
                SemanticValidationIssue(
                    code=SemanticIssueCode.CROSS_SOURCE,
                    message="source_name is required",
                )
            ],
        )

    mapping = reg.get_mapping(source)
    if mapping is None:
        return SemanticResolutionResult(
            status=SemanticMappingStatus.NOT_CONFIGURED,
            source_name=source,
            issues=[
                SemanticValidationIssue(
                    code=SemanticIssueCode.NOT_CONFIGURED,
                    message="no semantic mapping configured for source",
                )
            ],
        )

    try:
        resolved = resolve_active_revision(session, source)
    except CatalogQueryError:
        return SemanticResolutionResult(
            status=SemanticMappingStatus.INVALID,
            source_name=source,
            mapping_version=mapping.mapping_version,
            mapping_format_version=mapping.mapping_format_version,
            issues=[
                SemanticValidationIssue(
                    code=SemanticIssueCode.ACTIVE_CATALOG_NOT_FOUND,
                    message="active catalog revision not found for source",
                )
            ],
        )

    return validate_semantic_mapping(mapping, resolved)


def validate_semantic_mapping(
    mapping: SemanticMappingDocument,
    active: ResolvedActiveRevision,
) -> SemanticResolutionResult:
    """Deterministically validate ``mapping`` against one Active Catalog snapshot."""
    issues: list[SemanticValidationIssue] = []

    if mapping.mapping_format_version != MAPPING_FORMAT_VERSION:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.UNSUPPORTED_MAPPING_VERSION,
                message=(
                    f"unsupported mapping_format_version "
                    f"{mapping.mapping_format_version!r}; "
                    f"expected {MAPPING_FORMAT_VERSION!r}"
                ),
            )
        )

    if mapping.source_name != active.source_name:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.CROSS_SOURCE,
                message=(
                    f"mapping source_name {mapping.source_name!r} does not match "
                    f"active catalog source {active.source_name!r}"
                ),
            )
        )

    stale = False
    if mapping.catalog_revision_id != active.revision_id:
        stale = True
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.STALE_REVISION,
                message=(
                    f"mapping catalog_revision_id {mapping.catalog_revision_id} "
                    f"does not match active revision {active.revision_id}"
                ),
            )
        )
    if mapping.schema_fingerprint != active.schema_fingerprint:
        stale = True
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.STALE_FINGERPRINT,
                message=(
                    f"mapping schema_fingerprint {mapping.schema_fingerprint!r} "
                    f"does not match active fingerprint {active.schema_fingerprint!r}"
                ),
            )
        )

    index = _build_catalog_index(active)
    resource_keys = _collect_resource_keys(mapping, issues)
    _validate_resources(mapping, index, resource_keys, issues)

    status = _status_from_issues(issues, stale=stale)
    resources: list[ResolvedLogicalResource] = []
    if status is SemanticMappingStatus.VALID:
        resources = _resolve_resources(mapping, index)

    return SemanticResolutionResult(
        status=status,
        source_name=active.source_name,
        catalog_revision_id=active.revision_id,
        schema_fingerprint=active.schema_fingerprint,
        mapping_version=mapping.mapping_version,
        mapping_format_version=mapping.mapping_format_version,
        resources=resources,
        issues=issues,
    )


def _status_from_issues(
    issues: list[SemanticValidationIssue],
    *,
    stale: bool,
) -> SemanticMappingStatus:
    if not issues:
        return SemanticMappingStatus.VALID
    stale_only = all(
        str(issue.code)
        in {
            SemanticIssueCode.STALE_REVISION,
            SemanticIssueCode.STALE_FINGERPRINT,
        }
        for issue in issues
    )
    if stale and stale_only:
        return SemanticMappingStatus.STALE
    # Stale mixed with structural errors → INVALID (reject; do not treat as usable).
    if any(
        str(issue.code)
        not in {
            SemanticIssueCode.STALE_REVISION,
            SemanticIssueCode.STALE_FINGERPRINT,
        }
        for issue in issues
    ):
        return SemanticMappingStatus.INVALID
    return SemanticMappingStatus.STALE if stale else SemanticMappingStatus.INVALID


def _build_catalog_index(active: ResolvedActiveRevision) -> _CatalogSnapshotIndex:
    table_buckets: dict[tuple[str, str], list[Any]] = {}
    for raw in _doc_list(active.revision.tables_json, "tables"):
        item = _map_table(raw, {})
        table_buckets.setdefault(_table_key(item.schema_name, item.name), []).append(item)

    column_buckets: dict[tuple[str, str], dict[str, list[Any]]] = {}
    for raw in _doc_list(active.revision.columns_json, "columns"):
        item = _map_column(raw)
        tkey = _table_key(item.schema_name or "", item.table_name)
        col_map = column_buckets.setdefault(tkey, {})
        col_map.setdefault(item.name.casefold(), []).append(item)

    relations_by_key: dict[tuple[str, str, str, str, str], list[Any]] = {}
    for raw in _doc_list(active.revision.relations_json, "relations"):
        item = _map_relation(raw)
        if not item.name:
            continue
        rkey = (
            (item.schema_name or "").casefold(),
            item.table_name.casefold(),
            (item.referenced_schema_name or "").casefold(),
            item.referenced_table_name.casefold(),
            item.name.casefold(),
        )
        relations_by_key.setdefault(rkey, []).append(item)

    return _CatalogSnapshotIndex(
        tables=table_buckets,
        columns=column_buckets,
        relations_by_key=relations_by_key,
    )


def _table_key(schema_name: str, table_name: str) -> tuple[str, str]:
    return (schema_name.casefold(), table_name.casefold())


def _collect_resource_keys(
    mapping: SemanticMappingDocument,
    issues: list[SemanticValidationIssue],
) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for resource in mapping.resources:
        if resource.resource_key in seen:
            duplicates.add(resource.resource_key)
        seen.add(resource.resource_key)
    for key in sorted(duplicates):
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.DUPLICATE_RESOURCE_KEY,
                message=f"duplicate resource_key {key!r}",
                resource_key=key,
            )
        )
    return seen


def _validate_resources(
    mapping: SemanticMappingDocument,
    index: _CatalogSnapshotIndex,
    resource_keys: set[str],
    issues: list[SemanticValidationIssue],
) -> None:
    relationship_keys_seen: set[str] = set()
    for resource in mapping.resources:
        _validate_table(resource, index, issues)
        _validate_fields(resource, index, issues)
        for rel in resource.relationships:
            if rel.relationship_key in relationship_keys_seen:
                issues.append(
                    SemanticValidationIssue(
                        code=SemanticIssueCode.DUPLICATE_RELATIONSHIP_KEY,
                        message=f"duplicate relationship_key {rel.relationship_key!r}",
                        resource_key=resource.resource_key,
                        relationship_key=rel.relationship_key,
                    )
                )
            relationship_keys_seen.add(rel.relationship_key)
            _validate_relationship(resource, rel, resource_keys, index, issues)


def _validate_table(
    resource: LogicalResourceDefinition,
    index: _CatalogSnapshotIndex,
    issues: list[SemanticValidationIssue],
) -> None:
    key = _table_key(resource.physical_table.schema_name, resource.physical_table.table_name)
    matches = index.tables.get(key, [])
    if not matches:
        # Ambiguous without schema: same table_name in multiple schemas.
        name_matches = [
            items
            for (schema, table), items in index.tables.items()
            if table == resource.physical_table.table_name.casefold()
        ]
        flat = [item for bucket in name_matches for item in bucket]
        if len(flat) > 1 and not resource.physical_table.schema_name:
            issues.append(
                SemanticValidationIssue(
                    code=SemanticIssueCode.AMBIGUOUS_TABLE,
                    message=(
                        f"ambiguous table_name {resource.physical_table.table_name!r} "
                        "across schemas"
                    ),
                    resource_key=resource.resource_key,
                )
            )
        else:
            issues.append(
                SemanticValidationIssue(
                    code=SemanticIssueCode.MISSING_TABLE,
                    message=(
                        f"table {resource.physical_table.schema_name}."
                        f"{resource.physical_table.table_name} not found in active catalog"
                    ),
                    resource_key=resource.resource_key,
                )
            )
        return
    if len(matches) > 1:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.AMBIGUOUS_TABLE,
                message=(
                    f"ambiguous table {resource.physical_table.schema_name}."
                    f"{resource.physical_table.table_name} in active catalog"
                ),
                resource_key=resource.resource_key,
            )
        )


def _validate_fields(
    resource: LogicalResourceDefinition,
    index: _CatalogSnapshotIndex,
    issues: list[SemanticValidationIssue],
) -> None:
    seen_fields: set[str] = set()
    for field_def in resource.fields:
        if field_def.field_key in seen_fields:
            issues.append(
                SemanticValidationIssue(
                    code=SemanticIssueCode.DUPLICATE_FIELD_KEY,
                    message=f"duplicate field_key {field_def.field_key!r}",
                    resource_key=resource.resource_key,
                    field_key=field_def.field_key,
                )
            )
        seen_fields.add(field_def.field_key)

        for capability in field_def.capabilities:
            if not is_approved_capability(str(capability)):
                issues.append(
                    SemanticValidationIssue(
                        code=SemanticIssueCode.UNKNOWN_CAPABILITY,
                        message=f"unapproved field capability {capability!r}",
                        resource_key=resource.resource_key,
                        field_key=field_def.field_key,
                    )
                )

        # Field must bind to the resource's physical table.
        if (
            field_def.physical_column.schema_name.casefold()
            != resource.physical_table.schema_name.casefold()
            or field_def.physical_column.table_name.casefold()
            != resource.physical_table.table_name.casefold()
        ):
            issues.append(
                SemanticValidationIssue(
                    code=SemanticIssueCode.INVALID_RELATIONSHIP,
                    message=(
                        f"field {field_def.field_key!r} physical_column is not on "
                        f"resource table {resource.physical_table.schema_name}."
                        f"{resource.physical_table.table_name}"
                    ),
                    resource_key=resource.resource_key,
                    field_key=field_def.field_key,
                )
            )

        _validate_column(resource.resource_key, field_def, index, issues)


def _validate_column(
    resource_key: str,
    field_def: LogicalFieldDefinition,
    index: _CatalogSnapshotIndex,
    issues: list[SemanticValidationIssue],
) -> None:
    tkey = _table_key(
        field_def.physical_column.schema_name,
        field_def.physical_column.table_name,
    )
    col_map = index.columns.get(tkey)
    if col_map is None:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.MISSING_COLUMN,
                message=(
                    f"column {field_def.physical_column.schema_name}."
                    f"{field_def.physical_column.table_name}."
                    f"{field_def.physical_column.column_name} not found "
                    "(table has no columns in active catalog)"
                ),
                resource_key=resource_key,
                field_key=field_def.field_key,
            )
        )
        return
    matches = col_map.get(field_def.physical_column.column_name.casefold(), [])
    if not matches:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.MISSING_COLUMN,
                message=(
                    f"column {field_def.physical_column.schema_name}."
                    f"{field_def.physical_column.table_name}."
                    f"{field_def.physical_column.column_name} not found in active catalog"
                ),
                resource_key=resource_key,
                field_key=field_def.field_key,
            )
        )
        return
    if len(matches) > 1:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.AMBIGUOUS_COLUMN,
                message=(
                    f"ambiguous column {field_def.physical_column.column_name!r} "
                    f"on {field_def.physical_column.schema_name}."
                    f"{field_def.physical_column.table_name}"
                ),
                resource_key=resource_key,
                field_key=field_def.field_key,
            )
        )


def _validate_relationship(
    resource: LogicalResourceDefinition,
    rel: LogicalRelationshipDefinition,
    resource_keys: set[str],
    index: _CatalogSnapshotIndex,
    issues: list[SemanticValidationIssue],
) -> None:
    if rel.from_resource_key != resource.resource_key:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.INVALID_RELATIONSHIP,
                message=(
                    f"relationship {rel.relationship_key!r} from_resource_key "
                    f"{rel.from_resource_key!r} must equal owning resource "
                    f"{resource.resource_key!r}"
                ),
                resource_key=resource.resource_key,
                relationship_key=rel.relationship_key,
            )
        )
    if rel.from_resource_key not in resource_keys:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.INVALID_RELATIONSHIP,
                message=f"from_resource_key {rel.from_resource_key!r} is not defined",
                resource_key=resource.resource_key,
                relationship_key=rel.relationship_key,
            )
        )
    if rel.to_resource_key not in resource_keys:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.INVALID_RELATIONSHIP,
                message=f"to_resource_key {rel.to_resource_key!r} is not defined",
                resource_key=resource.resource_key,
                relationship_key=rel.relationship_key,
            )
        )

    fk = rel.catalog_fk
    # Source side of FK should match the owning resource's physical table.
    if (
        fk.source_schema_name.casefold() != resource.physical_table.schema_name.casefold()
        or fk.source_table_name.casefold() != resource.physical_table.table_name.casefold()
    ):
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.INVALID_RELATIONSHIP,
                message=(
                    f"relationship {rel.relationship_key!r} catalog_fk source table "
                    "does not match owning resource physical_table"
                ),
                resource_key=resource.resource_key,
                relationship_key=rel.relationship_key,
            )
        )

    matches = _find_fk_matches(fk, index)
    if not matches:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.MISSING_FK,
                message=(
                    f"catalog FK {fk.constraint_name!r} "
                    f"{fk.source_schema_name}.{fk.source_table_name} -> "
                    f"{fk.target_schema_name}.{fk.target_table_name} "
                    "not found in active catalog"
                ),
                resource_key=resource.resource_key,
                relationship_key=rel.relationship_key,
            )
        )
        return
    if len(matches) > 1:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.AMBIGUOUS_FK,
                message=(
                    f"catalog FK {fk.constraint_name!r} matches multiple "
                    "relations in active catalog"
                ),
                resource_key=resource.resource_key,
                relationship_key=rel.relationship_key,
            )
        )
        return

    catalog_rel = matches[0]
    expected = [(m.source_column.casefold(), m.target_column.casefold()) for m in fk.column_mappings]
    actual = [
        (m.column.casefold(), m.referenced_column.casefold()) for m in catalog_rel.columns
    ]
    if expected != actual:
        issues.append(
            SemanticValidationIssue(
                code=SemanticIssueCode.INVALID_RELATIONSHIP,
                message=(
                    f"relationship {rel.relationship_key!r} column_mappings "
                    "do not match catalog FK column mapping"
                ),
                resource_key=resource.resource_key,
                relationship_key=rel.relationship_key,
            )
        )


def _find_fk_matches(fk: CatalogFkBinding, index: _CatalogSnapshotIndex) -> list[Any]:
    rkey = (
        fk.source_schema_name.casefold(),
        fk.source_table_name.casefold(),
        fk.target_schema_name.casefold(),
        fk.target_table_name.casefold(),
        fk.constraint_name.casefold(),
    )
    return list(index.relations_by_key.get(rkey, []))


def _resolve_resources(
    mapping: SemanticMappingDocument,
    index: _CatalogSnapshotIndex,
) -> list[ResolvedLogicalResource]:
    resolved: list[ResolvedLogicalResource] = []
    for resource in mapping.resources:
        fields: list[ResolvedLogicalField] = []
        for field_def in resource.fields:
            tkey = _table_key(
                field_def.physical_column.schema_name,
                field_def.physical_column.table_name,
            )
            col_matches = index.columns.get(tkey, {}).get(
                field_def.physical_column.column_name.casefold(), []
            )
            catalog_type = col_matches[0].data_type if col_matches else None
            fields.append(
                ResolvedLogicalField(
                    field_key=field_def.field_key,
                    description=field_def.description,
                    data_type=field_def.data_type,
                    physical_column=field_def.physical_column,
                    catalog_data_type=catalog_type,
                    capabilities=[str(c) for c in field_def.capabilities],
                )
            )
        relationships = [
            ResolvedLogicalRelationship(
                relationship_key=rel.relationship_key,
                description=rel.description,
                from_resource_key=rel.from_resource_key,
                to_resource_key=rel.to_resource_key,
                catalog_fk=rel.catalog_fk,
            )
            for rel in resource.relationships
        ]
        resolved.append(
            ResolvedLogicalResource(
                resource_key=resource.resource_key,
                description=resource.description,
                physical_table=resource.physical_table,
                fields=fields,
                relationships=relationships,
            )
        )
    return resolved


__all__ = [
    "SemanticResourceRegistry",
    "get_default_semantic_registry",
    "resolve_semantic_resources",
    "validate_semantic_mapping",
]
