"""Structured Query Plan validation (Phase 29-B).

Resolves Active Catalog + Semantic Resource mapping, validates a caller plan
against explicit logical capabilities, and returns an immutable validation-only
logical plan. Does not compile SQL, issue execution tokens, or approve mappings.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.domain.semantic_resource import FieldCapability, SemanticMappingStatus
from app.domain.structured_query_plan import (
    LIST_OPERATORS,
    MAX_IN_LIST_SIZE,
    MAX_STRING_VALUE_LENGTH,
    NULLARY_OPERATORS,
    NUMERIC_AGGREGATIONS,
    OPERATORS_BY_TYPE,
    PLAN_FORMAT_VERSION,
    AggregationFunction,
    FilterOperator,
    LogicalDataType,
    PlanIssueCode,
    PlanValidationStatus,
    SortDirection,
    normalize_logical_data_type,
)
from app.schemas.semantic_resource import (
    ResolvedLogicalField,
    ResolvedLogicalRelationship,
    ResolvedLogicalResource,
    SemanticResolutionResult,
)
from app.schemas.structured_query_plan import (
    PlanAggregationSpec,
    PlanFilterPredicate,
    PlanValidationIssue,
    StructuredQueryPlan,
    ValidatedAggregationSpec,
    ValidatedFieldRef,
    ValidatedFilterPredicate,
    ValidatedLogicalPlan,
    ValidatedSortSpec,
)
from app.services.semantic_resource import (
    SemanticResourceRegistry,
    get_default_semantic_registry,
    resolve_semantic_resources,
)

# Patterns that must never appear in filter string values (defense in depth).
_FORBIDDEN_VALUE_FRAGMENTS = (
    ";",
    "--",
    "/*",
    "*/",
    "\x00",
)


def validate_structured_query_plan(
    session: Session,
    plan: StructuredQueryPlan,
    *,
    registry: SemanticResourceRegistry | None = None,
) -> ValidatedLogicalPlan:
    """Validate ``plan`` against Active Catalog + Semantic Resource mapping.

    Test-only injected registries are permitted. The default empty registry
    fails closed as ``NOT_CONFIGURED``. A valid mapping alone does not imply
    approval or executability — output is always validation-only.
    """
    reg = registry if registry is not None else get_default_semantic_registry()
    issues: list[PlanValidationIssue] = []

    if plan.plan_format_version != PLAN_FORMAT_VERSION:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.UNSUPPORTED_PLAN_VERSION,
                message=(
                    f"unsupported plan_format_version {plan.plan_format_version!r}; "
                    f"expected {PLAN_FORMAT_VERSION!r}"
                ),
            )
        )
        return _failure_plan(
            plan,
            status=PlanValidationStatus.INVALID,
            issues=issues,
        )

    semantic = resolve_semantic_resources(session, plan.source_name, registry=reg)
    gate = _gate_semantic_status(plan, semantic, issues)
    if gate is not None:
        return gate

    resource = _find_resource(semantic, plan.resource_key)
    if resource is None:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.UNKNOWN_RESOURCE,
                message=f"unknown resource_key {plan.resource_key!r}",
            )
        )
        return _failure_plan(
            plan,
            status=PlanValidationStatus.INVALID,
            issues=issues,
            semantic=semantic,
        )

    fields_by_key = {f.field_key: f for f in resource.fields}
    relationships_by_key = {r.relationship_key: r for r in resource.relationships}

    select_refs = _validate_select(plan, resource, fields_by_key, issues)
    filter_refs = _validate_filters(plan, resource, fields_by_key, issues)
    sort_refs = _validate_sort(plan, resource, fields_by_key, issues)
    group_refs = _validate_group_by(plan, resource, fields_by_key, issues)
    agg_refs = _validate_aggregations(plan, resource, fields_by_key, issues)
    rel_keys = _validate_relationships(plan, resource, relationships_by_key, issues)
    _validate_grouping_consistency(plan, issues)

    if issues:
        return _failure_plan(
            plan,
            status=PlanValidationStatus.INVALID,
            issues=issues,
            semantic=semantic,
            resource_key=resource.resource_key,
        )

    return ValidatedLogicalPlan(
        validation_only=True,
        executable=False,
        approved=False,
        status=PlanValidationStatus.VALID,
        plan_format_version=plan.plan_format_version,
        source_name=semantic.source_name,
        catalog_revision_id=semantic.catalog_revision_id,
        schema_fingerprint=semantic.schema_fingerprint,
        mapping_version=semantic.mapping_version,
        resource_key=resource.resource_key,
        select=tuple(select_refs),
        filters=tuple(filter_refs),
        sort=tuple(sort_refs),
        group_by=tuple(group_refs),
        aggregations=tuple(agg_refs),
        relationships=tuple(rel_keys),
        limit=plan.limit,
        issues=(),
    )


def _gate_semantic_status(
    plan: StructuredQueryPlan,
    semantic: SemanticResolutionResult,
    issues: list[PlanValidationIssue],
) -> ValidatedLogicalPlan | None:
    status = SemanticMappingStatus(str(semantic.status))
    if status is SemanticMappingStatus.NOT_CONFIGURED:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.NOT_CONFIGURED,
                message="semantic mapping is NOT_CONFIGURED for source",
            )
        )
        return _failure_plan(
            plan,
            status=PlanValidationStatus.NOT_CONFIGURED,
            issues=issues,
            semantic=semantic,
        )
    if status is SemanticMappingStatus.STALE:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.STALE_MAPPING,
                message="semantic mapping is STALE relative to active catalog",
            )
        )
        return _failure_plan(
            plan,
            status=PlanValidationStatus.STALE,
            issues=issues,
            semantic=semantic,
        )
    if status is SemanticMappingStatus.INVALID:
        # Preserve cross-source signal when present on the semantic result.
        if any(str(i.code) == "CROSS_SOURCE" for i in semantic.issues):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.CROSS_SOURCE,
                    message="semantic mapping source does not match active catalog",
                )
            )
        else:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.SEMANTIC_MAPPING_INVALID,
                    message="semantic mapping is INVALID for source",
                )
            )
        return _failure_plan(
            plan,
            status=PlanValidationStatus.INVALID,
            issues=issues,
            semantic=semantic,
        )
    if status is not SemanticMappingStatus.VALID:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.SEMANTIC_MAPPING_INVALID,
                message=f"unexpected semantic mapping status {semantic.status!r}",
            )
        )
        return _failure_plan(
            plan,
            status=PlanValidationStatus.INVALID,
            issues=issues,
            semantic=semantic,
        )
    return None


def _find_resource(
    semantic: SemanticResolutionResult, resource_key: str
) -> ResolvedLogicalResource | None:
    matches = [r for r in semantic.resources if r.resource_key == resource_key]
    if len(matches) != 1:
        return None
    return matches[0]


def _validate_select(
    plan: StructuredQueryPlan,
    resource: ResolvedLogicalResource,
    fields_by_key: dict[str, ResolvedLogicalField],
    issues: list[PlanValidationIssue],
) -> list[ValidatedFieldRef]:
    refs: list[ValidatedFieldRef] = []
    seen: set[str] = set()
    for field_key in plan.select:
        if field_key in seen:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.COMPLEXITY_EXCEEDED,
                    message=f"duplicate select field_key {field_key!r}",
                    field_key=field_key,
                )
            )
            continue
        seen.add(field_key)
        field = _require_field(field_key, fields_by_key, issues)
        if field is None:
            continue
        if not _has_capability(field, FieldCapability.SELECT):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.MISSING_CAPABILITY,
                    message=f"field {field_key!r} lacks SELECT capability",
                    field_key=field_key,
                )
            )
            continue
        refs.append(
            ValidatedFieldRef(
                field_key=field.field_key,
                data_type=field.data_type,
                resource_key=resource.resource_key,
            )
        )
    return refs


def _validate_filters(
    plan: StructuredQueryPlan,
    resource: ResolvedLogicalResource,
    fields_by_key: dict[str, ResolvedLogicalField],
    issues: list[PlanValidationIssue],
) -> list[ValidatedFilterPredicate]:
    refs: list[ValidatedFilterPredicate] = []
    for predicate in plan.filters:
        field = _require_field(predicate.field_key, fields_by_key, issues)
        if field is None:
            continue
        if not _has_capability(field, FieldCapability.FILTER):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.MISSING_CAPABILITY,
                    message=f"field {predicate.field_key!r} lacks FILTER capability",
                    field_key=predicate.field_key,
                )
            )
            continue
        logical_type = normalize_logical_data_type(field.data_type)
        if logical_type is None:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.UNSUPPORTED_OPERATOR,
                    message=(
                        f"field {predicate.field_key!r} has unsupported data_type "
                        f"{field.data_type!r}"
                    ),
                    field_key=predicate.field_key,
                )
            )
            continue
        operator = FilterOperator(str(predicate.operator))
        allowed = OPERATORS_BY_TYPE[logical_type]
        if operator not in allowed:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.UNSUPPORTED_OPERATOR,
                    message=(
                        f"operator {operator.value} is not allowed for data_type "
                        f"{logical_type.value}"
                    ),
                    field_key=predicate.field_key,
                )
            )
            continue
        normalized_value = _validate_filter_value(
            predicate, logical_type, operator, issues
        )
        if normalized_value is _VALUE_INVALID:
            continue
        refs.append(
            ValidatedFilterPredicate(
                field_key=field.field_key,
                data_type=field.data_type,
                operator=operator.value,  # type: ignore[arg-type]
                value=normalized_value,
            )
        )
    return refs


_VALUE_INVALID = object()


def _validate_filter_value(
    predicate: PlanFilterPredicate,
    logical_type: LogicalDataType,
    operator: FilterOperator,
    issues: list[PlanValidationIssue],
) -> Any:
    value = predicate.value
    if operator in NULLARY_OPERATORS:
        if value is not None:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_FILTER_VALUE,
                    message=f"operator {operator.value} requires value=null",
                    field_key=predicate.field_key,
                )
            )
            return _VALUE_INVALID
        return None

    if operator in LIST_OPERATORS:
        if not isinstance(value, list) or len(value) == 0:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_FILTER_VALUE,
                    message=f"operator {operator.value} requires a non-empty list value",
                    field_key=predicate.field_key,
                )
            )
            return _VALUE_INVALID
        if len(value) > MAX_IN_LIST_SIZE:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.COMPLEXITY_EXCEEDED,
                    message=(
                        f"IN/NOT_IN list size {len(value)} exceeds max "
                        f"{MAX_IN_LIST_SIZE}"
                    ),
                    field_key=predicate.field_key,
                )
            )
            return _VALUE_INVALID
        normalized_items: list[Any] = []
        for item in value:
            item_norm = _coerce_scalar(item, logical_type, predicate.field_key, issues)
            if item_norm is _VALUE_INVALID:
                return _VALUE_INVALID
            normalized_items.append(item_norm)
        # Immutable sequence; JSON serialization remains a JSON array.
        return tuple(normalized_items)

    if operator is FilterOperator.BETWEEN:
        if not isinstance(value, list) or len(value) != 2:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_FILTER_VALUE,
                    message="operator BETWEEN requires a two-element list value",
                    field_key=predicate.field_key,
                )
            )
            return _VALUE_INVALID
        lo = _coerce_scalar(value[0], logical_type, predicate.field_key, issues)
        hi = _coerce_scalar(value[1], logical_type, predicate.field_key, issues)
        if lo is _VALUE_INVALID or hi is _VALUE_INVALID:
            return _VALUE_INVALID
        return (lo, hi)

    # Scalar operators (EQ/NE/LT/.../LIKE).
    if isinstance(value, list):
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_FILTER_VALUE,
                message=f"operator {operator.value} requires a scalar value",
                field_key=predicate.field_key,
            )
        )
        return _VALUE_INVALID
    return _coerce_scalar(value, logical_type, predicate.field_key, issues)


def _coerce_scalar(
    value: Any,
    logical_type: LogicalDataType,
    field_key: str,
    issues: list[PlanValidationIssue],
) -> Any:
    if value is None:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_FILTER_VALUE,
                message="null value is only valid with IS_NULL / IS_NOT_NULL",
                field_key=field_key,
            )
        )
        return _VALUE_INVALID

    if logical_type is LogicalDataType.INTEGER:
        if isinstance(value, bool) or not isinstance(value, int):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_FILTER_VALUE,
                    message="expected integer filter value",
                    field_key=field_key,
                )
            )
            return _VALUE_INVALID
        return value

    if logical_type is LogicalDataType.NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_FILTER_VALUE,
                    message="expected number filter value",
                    field_key=field_key,
                )
            )
            return _VALUE_INVALID
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_FILTER_VALUE,
                    message="number filter value must be finite (reject NaN/Infinity)",
                    field_key=field_key,
                )
            )
            return _VALUE_INVALID
        return float(value) if isinstance(value, float) else value

    if logical_type is LogicalDataType.BOOLEAN:
        if not isinstance(value, bool):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_FILTER_VALUE,
                    message="expected boolean filter value",
                    field_key=field_key,
                )
            )
            return _VALUE_INVALID
        return value

    if logical_type is LogicalDataType.DATE:
        return _normalize_iso_date(value, field_key, issues)

    if logical_type is LogicalDataType.DATETIME:
        return _normalize_iso_datetime(value, field_key, issues)

    if logical_type is LogicalDataType.STRING:
        if not isinstance(value, str):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_FILTER_VALUE,
                    message="expected string filter value for string",
                    field_key=field_key,
                )
            )
            return _VALUE_INVALID
        if len(value) > MAX_STRING_VALUE_LENGTH:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.COMPLEXITY_EXCEEDED,
                    message=(
                        f"string filter value length exceeds "
                        f"{MAX_STRING_VALUE_LENGTH}"
                    ),
                    field_key=field_key,
                )
            )
            return _VALUE_INVALID
        lowered = value.casefold()
        for fragment in _FORBIDDEN_VALUE_FRAGMENTS:
            if fragment in value or fragment in lowered:
                issues.append(
                    PlanValidationIssue(
                        code=PlanIssueCode.FORBIDDEN_INPUT,
                        message="filter value contains forbidden SQL-shaped fragment",
                        field_key=field_key,
                    )
                )
                return _VALUE_INVALID
        return value

    issues.append(
        PlanValidationIssue(
            code=PlanIssueCode.INVALID_FILTER_VALUE,
            message=f"unsupported logical data type {logical_type.value}",
            field_key=field_key,
        )
    )
    return _VALUE_INVALID


def _normalize_iso_date(
    value: Any,
    field_key: str,
    issues: list[PlanValidationIssue],
) -> Any:
    if not isinstance(value, str):
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_FILTER_VALUE,
                message="expected ISO-8601 date string (YYYY-MM-DD)",
                field_key=field_key,
            )
        )
        return _VALUE_INVALID
    if len(value) > MAX_STRING_VALUE_LENGTH:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.COMPLEXITY_EXCEEDED,
                message=f"date filter value length exceeds {MAX_STRING_VALUE_LENGTH}",
                field_key=field_key,
            )
        )
        return _VALUE_INVALID
    # Strict calendar date only — reject datetimes and malformed/impossible dates.
    if "T" in value or " " in value or "t" in value:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_FILTER_VALUE,
                message="date filter value must be ISO-8601 calendar date (YYYY-MM-DD)",
                field_key=field_key,
            )
        )
        return _VALUE_INVALID
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_FILTER_VALUE,
                message="date filter value is not a valid ISO-8601 calendar date",
                field_key=field_key,
            )
        )
        return _VALUE_INVALID
    return parsed.isoformat()


def _normalize_iso_datetime(
    value: Any,
    field_key: str,
    issues: list[PlanValidationIssue],
) -> Any:
    if not isinstance(value, str):
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_FILTER_VALUE,
                message="expected ISO-8601 datetime string",
                field_key=field_key,
            )
        )
        return _VALUE_INVALID
    if len(value) > MAX_STRING_VALUE_LENGTH:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.COMPLEXITY_EXCEEDED,
                message=(
                    f"datetime filter value length exceeds {MAX_STRING_VALUE_LENGTH}"
                ),
                field_key=field_key,
            )
        )
        return _VALUE_INVALID
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_FILTER_VALUE,
                message="datetime filter value is not a valid ISO-8601 datetime",
                field_key=field_key,
            )
        )
        return _VALUE_INVALID
    # Reject bare dates that Python accepts as midnight datetimes when callers
    # declared datetime — require an explicit time component.
    if "T" not in value and "t" not in value and " " not in value:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_FILTER_VALUE,
                message="datetime filter value must include a time component",
                field_key=field_key,
            )
        )
        return _VALUE_INVALID
    return parsed.isoformat()


def _validate_sort(
    plan: StructuredQueryPlan,
    resource: ResolvedLogicalResource,
    fields_by_key: dict[str, ResolvedLogicalField],
    issues: list[PlanValidationIssue],
) -> list[ValidatedSortSpec]:
    refs: list[ValidatedSortSpec] = []
    group_set = set(plan.group_by)
    for spec in plan.sort:
        field = _require_field(spec.field_key, fields_by_key, issues)
        if field is None:
            continue
        if not _has_capability(field, FieldCapability.SORT):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.MISSING_CAPABILITY,
                    message=f"field {spec.field_key!r} lacks SORT capability",
                    field_key=spec.field_key,
                )
            )
            continue
        if plan.aggregations and spec.field_key not in group_set:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_GROUPING,
                    message=(
                        f"sort field {spec.field_key!r} must appear in group_by "
                        "when aggregations are present"
                    ),
                    field_key=spec.field_key,
                )
            )
            continue
        direction = SortDirection(str(spec.direction))
        refs.append(
            ValidatedSortSpec(
                field_key=field.field_key,
                direction=direction.value,  # type: ignore[arg-type]
            )
        )
    return refs


def _validate_group_by(
    plan: StructuredQueryPlan,
    resource: ResolvedLogicalResource,
    fields_by_key: dict[str, ResolvedLogicalField],
    issues: list[PlanValidationIssue],
) -> list[ValidatedFieldRef]:
    refs: list[ValidatedFieldRef] = []
    seen: set[str] = set()
    for field_key in plan.group_by:
        if field_key in seen:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.COMPLEXITY_EXCEEDED,
                    message=f"duplicate group_by field_key {field_key!r}",
                    field_key=field_key,
                )
            )
            continue
        seen.add(field_key)
        field = _require_field(field_key, fields_by_key, issues)
        if field is None:
            continue
        if not _has_capability(field, FieldCapability.GROUP_BY):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.MISSING_CAPABILITY,
                    message=f"field {field_key!r} lacks GROUP_BY capability",
                    field_key=field_key,
                )
            )
            continue
        refs.append(
            ValidatedFieldRef(
                field_key=field.field_key,
                data_type=field.data_type,
                resource_key=resource.resource_key,
            )
        )
    return refs


def _validate_aggregations(
    plan: StructuredQueryPlan,
    resource: ResolvedLogicalResource,
    fields_by_key: dict[str, ResolvedLogicalField],
    issues: list[PlanValidationIssue],
) -> list[ValidatedAggregationSpec]:
    refs: list[ValidatedAggregationSpec] = []
    for spec in plan.aggregations:
        field = _require_field(spec.field_key, fields_by_key, issues)
        if field is None:
            continue
        if not _has_capability(field, FieldCapability.AGGREGATE):
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.MISSING_CAPABILITY,
                    message=f"field {spec.field_key!r} lacks AGGREGATE capability",
                    field_key=spec.field_key,
                )
            )
            continue
        function = AggregationFunction(str(spec.function))
        logical_type = normalize_logical_data_type(field.data_type)
        if function in NUMERIC_AGGREGATIONS and logical_type not in {
            LogicalDataType.INTEGER,
            LogicalDataType.NUMBER,
        }:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.UNSUPPORTED_AGGREGATION,
                    message=(
                        f"aggregation {function.value} requires numeric field; "
                        f"got data_type {field.data_type!r}"
                    ),
                    field_key=spec.field_key,
                )
            )
            continue
        refs.append(
            ValidatedAggregationSpec(
                function=function.value,  # type: ignore[arg-type]
                field_key=field.field_key,
                alias=spec.alias,
                data_type=field.data_type,
            )
        )
    return refs


def _validate_relationships(
    plan: StructuredQueryPlan,
    resource: ResolvedLogicalResource,
    relationships_by_key: dict[str, ResolvedLogicalRelationship],
    issues: list[PlanValidationIssue],
) -> list[str]:
    if not plan.relationships:
        # Multiple outbound relationships without an explicit key choice are
        # ambiguous for future join compilation — fail closed when >1 exist and
        # the plan requests no relationships but also doesn't need joins.
        # Ambiguity only applies when relationships are requested incorrectly.
        return []

    selected: list[str] = []
    seen: set[str] = set()
    for key in plan.relationships:
        if key in seen:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.DUPLICATE_RELATIONSHIP,
                    message=f"duplicate relationship_key {key!r}",
                    relationship_key=key,
                )
            )
            continue
        seen.add(key)
        rel = relationships_by_key.get(key)
        if rel is None:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.UNKNOWN_RELATIONSHIP,
                    message=f"unknown relationship_key {key!r}",
                    relationship_key=key,
                )
            )
            continue
        selected.append(rel.relationship_key)

    # Ambiguous: same to_resource_key selected via multiple relationship keys.
    targets = [
        relationships_by_key[k].to_resource_key
        for k in selected
        if k in relationships_by_key
    ]
    if len(targets) != len(set(targets)):
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.AMBIGUOUS_JOIN,
                message="selected relationships target the same logical resource more than once",
            )
        )
    return selected


def _validate_grouping_consistency(
    plan: StructuredQueryPlan,
    issues: list[PlanValidationIssue],
) -> None:
    if plan.group_by and not plan.aggregations:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.INVALID_GROUPING,
                message="group_by requires at least one aggregation",
            )
        )
        return
    if not plan.aggregations:
        return
    group_set = set(plan.group_by)
    for field_key in plan.select:
        if field_key not in group_set:
            issues.append(
                PlanValidationIssue(
                    code=PlanIssueCode.INVALID_GROUPING,
                    message=(
                        f"select field {field_key!r} must appear in group_by "
                        "when aggregations are present"
                    ),
                    field_key=field_key,
                )
            )


def _require_field(
    field_key: str,
    fields_by_key: dict[str, ResolvedLogicalField],
    issues: list[PlanValidationIssue],
) -> ResolvedLogicalField | None:
    field = fields_by_key.get(field_key)
    if field is None:
        issues.append(
            PlanValidationIssue(
                code=PlanIssueCode.UNKNOWN_FIELD,
                message=f"unknown field_key {field_key!r}",
                field_key=field_key,
            )
        )
        return None
    return field


def _has_capability(field: ResolvedLogicalField, capability: FieldCapability) -> bool:
    return capability.value in {str(c) for c in field.capabilities}


def _failure_plan(
    plan: StructuredQueryPlan,
    *,
    status: PlanValidationStatus,
    issues: list[PlanValidationIssue],
    semantic: SemanticResolutionResult | None = None,
    resource_key: str | None = None,
) -> ValidatedLogicalPlan:
    return ValidatedLogicalPlan(
        validation_only=True,
        executable=False,
        approved=False,
        status=status,
        plan_format_version=plan.plan_format_version,
        source_name=plan.source_name,
        catalog_revision_id=semantic.catalog_revision_id if semantic else None,
        schema_fingerprint=semantic.schema_fingerprint if semantic else None,
        mapping_version=semantic.mapping_version if semantic else None,
        resource_key=resource_key or plan.resource_key,
        select=(),
        filters=(),
        sort=(),
        group_by=(),
        aggregations=(),
        relationships=(),
        limit=None,
        issues=tuple(issues),
    )


__all__ = [
    "validate_structured_query_plan",
]
