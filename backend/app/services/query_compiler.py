"""Deterministic Oracle SELECT compiler for Structured Query Plans (Phase 29-C).

Always revalidates the caller plan against Active Catalog + Semantic Resource
mapping. Never trusts a caller-supplied ValidatedLogicalPlan. Produces
preview-only SQL + binds; does not execute, approve, or open DEMIS.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.domain.query_compiler import (
    COMPILER_VERSION,
    ORACLE_IDENT_PATTERN,
    CompilerIssueCode,
    CompilerStatus,
)
from app.domain.structured_query_plan import (
    AggregationFunction,
    FilterOperator,
    LogicalDataType,
    PlanValidationStatus,
    SortDirection,
    normalize_logical_data_type,
)
from app.schemas.query_compiler import CompiledQueryResult, CompilerIssue
from app.schemas.query_template import QueryTemplateParameter
from app.schemas.semantic_resource import (
    ResolvedLogicalField,
    ResolvedLogicalRelationship,
    ResolvedLogicalResource,
)
from app.schemas.structured_query_plan import (
    StructuredQueryPlan,
    ValidatedFieldRef,
    ValidatedFilterPredicate,
    ValidatedLogicalPlan,
    ValidatedSortSpec,
)
from app.schemas.sql_safety import SqlSafetyReport
from app.services.semantic_resource import SemanticResourceRegistry
from app.services.sql_safety import validate_sql_safety
from app.services.structured_query_plan import validate_structured_query_plan

_IDENT_RE = re.compile(ORACLE_IDENT_PATTERN)
_ALIAS_RE = re.compile(r"^t\d+$")

_AGG_SQL = {
    AggregationFunction.COUNT: "COUNT",
    AggregationFunction.SUM: "SUM",
    AggregationFunction.AVG: "AVG",
    AggregationFunction.MIN: "MIN",
    AggregationFunction.MAX: "MAX",
}

_OP_SQL = {
    FilterOperator.EQ: "=",
    FilterOperator.NE: "<>",
    FilterOperator.LT: "<",
    FilterOperator.LE: "<=",
    FilterOperator.GT: ">",
    FilterOperator.GE: ">=",
    FilterOperator.LIKE: "LIKE",
}


@dataclass
class _BindBuilder:
    """Allocate unique Oracle-compatible named binds (:p1, :p2, …, :p_limit)."""

    parameters: dict[str, Any] = field(default_factory=dict)
    schema: list[QueryTemplateParameter] = field(default_factory=list)
    _counter: int = 0

    def add(self, value: Any, *, param_type: str, prefix: str = "p") -> str:
        self._counter += 1
        name = f"{prefix}{self._counter}"
        if not re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise ValueError(f"invalid bind name {name!r}")
        self.parameters[name] = value
        self.schema.append(
            QueryTemplateParameter(name=name, type=param_type, required=True)  # type: ignore[arg-type]
        )
        return name

    def add_limit(self, value: int) -> str:
        name = "p_limit"
        self.parameters[name] = value
        self.schema.append(
            QueryTemplateParameter(name=name, type="integer", required=True)
        )
        return name


def compile_structured_query_plan(
    session: Session,
    plan: StructuredQueryPlan,
    *,
    registry: SemanticResourceRegistry | None = None,
) -> CompiledQueryResult:
    """Compile a StructuredQueryPlan to preview-only Oracle SELECT SQL + binds.

    Server-side validation is always re-run. A caller-supplied
    ``ValidatedLogicalPlan`` is never accepted as trusted input.
    """
    validated = validate_structured_query_plan(session, plan, registry=registry)
    status = _map_plan_status(validated.status)
    if status is not CompilerStatus.VALID:
        return _failure(
            plan=plan,
            validated=validated,
            status=status,
            issues=_plan_gate_issues(validated),
        )

    # Re-resolve semantic resources for physical bindings (fields/relationships).
    # ValidatedLogicalPlan carries logical identities only.
    from app.services.semantic_resource import resolve_semantic_resources

    semantic = resolve_semantic_resources(
        session, plan.source_name, registry=registry
    )
    resource = next(
        (r for r in semantic.resources if r.resource_key == validated.resource_key),
        None,
    )
    if resource is None:
        return _failure(
            plan=plan,
            validated=validated,
            status=CompilerStatus.INVALID,
            issues=[
                CompilerIssue(
                    code=CompilerIssueCode.UNKNOWN_RESOURCE,
                    message=f"resource_key {validated.resource_key!r} missing after revalidation",
                )
            ],
        )

    issues: list[CompilerIssue] = []
    try:
        sql_text, binds, param_schema = _compile_oracle_select(
            validated, resource, semantic.resources, issues
        )
    except _CompileError as exc:
        return _failure(
            plan=plan,
            validated=validated,
            status=CompilerStatus.INVALID,
            issues=[
                CompilerIssue(code=exc.code, message=exc.message, field_key=exc.field_key)
            ],
        )

    if issues:
        return _failure(
            plan=plan,
            validated=validated,
            status=CompilerStatus.INVALID,
            issues=issues,
        )

    safety = validate_sql_safety(sql_text, param_schema)
    if not safety.safe:
        return _failure(
            plan=plan,
            validated=validated,
            status=CompilerStatus.INVALID,
            issues=[
                CompilerIssue(
                    code=CompilerIssueCode.SQL_SAFETY_FAILED,
                    message=f"compiled SQL failed safety validation: {safety.issues[0].message}",
                )
            ],
            sql_safety=safety,
        )

    return CompiledQueryResult(
        preview_only=True,
        validation_only=True,
        approved=False,
        executable=False,
        status=CompilerStatus.VALID,
        compiler_version=COMPILER_VERSION,
        source_name=validated.source_name,
        catalog_revision_id=validated.catalog_revision_id,
        schema_fingerprint=validated.schema_fingerprint,
        mapping_version=validated.mapping_version,
        resource_key=validated.resource_key,
        sql_text=sql_text,
        bind_parameters=dict(binds),
        sql_safety=safety,
        issues=(),
    )


class _CompileError(Exception):
    def __init__(
        self,
        code: CompilerIssueCode,
        message: str,
        *,
        field_key: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.field_key = field_key
        super().__init__(message)


def _compile_oracle_select(
    plan: ValidatedLogicalPlan,
    resource: ResolvedLogicalResource,
    all_resources: list[ResolvedLogicalResource],
    issues: list[CompilerIssue],
) -> tuple[str, dict[str, Any], list[QueryTemplateParameter]]:
    fields_by_key = {f.field_key: f for f in resource.fields}
    relationships_by_key = {r.relationship_key: r for r in resource.relationships}
    resources_by_key = {r.resource_key: r for r in all_resources}

    primary_alias = "t0"
    _assert_ident(resource.physical_table.schema_name, "schema")
    _assert_ident(resource.physical_table.table_name, "table")

    # Relationship aliases: t1..tn in declared relationship order.
    join_aliases: dict[str, str] = {}
    join_clauses: list[str] = []
    seen_targets: set[str] = set()
    for index, rel_key in enumerate(plan.relationships, start=1):
        rel = relationships_by_key.get(rel_key)
        if rel is None:
            raise _CompileError(
                CompilerIssueCode.UNKNOWN_RELATIONSHIP,
                f"unknown relationship_key {rel_key!r}",
            )
        if rel.to_resource_key in seen_targets:
            raise _CompileError(
                CompilerIssueCode.AMBIGUOUS_JOIN,
                f"ambiguous join: multiple relationships target {rel.to_resource_key!r}",
            )
        seen_targets.add(rel.to_resource_key)
        target = resources_by_key.get(rel.to_resource_key)
        if target is None:
            raise _CompileError(
                CompilerIssueCode.UNKNOWN_RESOURCE,
                f"relationship target resource {rel.to_resource_key!r} not found",
            )
        alias = f"t{index}"
        if not _ALIAS_RE.fullmatch(alias):
            raise _CompileError(
                CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
                f"invalid generated alias {alias!r}",
            )
        join_aliases[rel_key] = alias
        _assert_ident(target.physical_table.schema_name, "schema")
        _assert_ident(target.physical_table.table_name, "table")
        on_parts: list[str] = []
        for mapping in rel.catalog_fk.column_mappings:
            _assert_ident(mapping.source_column, "column")
            _assert_ident(mapping.target_column, "column")
            on_parts.append(
                f"{primary_alias}.{_q(mapping.source_column)} = "
                f"{alias}.{_q(mapping.target_column)}"
            )
        if not on_parts:
            raise _CompileError(
                CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
                f"relationship {rel_key!r} has empty FK column mappings",
            )
        join_clauses.append(
            "INNER JOIN "
            f"{_q(target.physical_table.schema_name)}."
            f"{_q(target.physical_table.table_name)} {alias} "
            f"ON {' AND '.join(on_parts)}"
        )

    binds = _BindBuilder()
    select_sql = _compile_select_list(plan, fields_by_key, primary_alias)
    from_sql = (
        f"FROM {_q(resource.physical_table.schema_name)}."
        f"{_q(resource.physical_table.table_name)} {primary_alias}"
    )
    join_sql = " ".join(join_clauses)
    where_sql = _compile_where(plan.filters, fields_by_key, primary_alias, binds)
    group_sql = _compile_group_by(plan.group_by, fields_by_key, primary_alias)
    order_sql = _compile_order_by(plan.sort, fields_by_key, primary_alias)
    if plan.limit is None:
        raise _CompileError(
            CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
            "validated plan is missing bounded limit",
        )
    limit_name = binds.add_limit(int(plan.limit))

    # Inner query holds projection/filter/join/group/order; outer applies ROWNUM.
    inner_parts = [
        f"SELECT {select_sql}",
        from_sql,
    ]
    if join_sql:
        inner_parts.append(join_sql)
    if where_sql:
        inner_parts.append(where_sql)
    if group_sql:
        inner_parts.append(group_sql)
    if order_sql:
        inner_parts.append(order_sql)
    inner_sql = " ".join(inner_parts)

    outer_select = ", ".join(
        f'q.{_q(_output_alias(item))}' for item in _projection_aliases(plan)
    )
    sql_text = (
        f"SELECT {outer_select} FROM ({inner_sql}) q "
        f"WHERE ROWNUM <= :{limit_name}"
    )
    return sql_text, binds.parameters, binds.schema


def _projection_aliases(plan: ValidatedLogicalPlan) -> list[str]:
    aliases = [ref.field_key for ref in plan.select]
    for agg in plan.aggregations:
        aliases.append(agg.alias or f"{str(agg.function).lower()}_{agg.field_key}")
    return aliases


def _output_alias(name: str) -> str:
    _assert_ident(name, "alias")
    return name


def _compile_select_list(
    plan: ValidatedLogicalPlan,
    fields_by_key: dict[str, ResolvedLogicalField],
    alias: str,
) -> str:
    parts: list[str] = []
    for ref in plan.select:
        field = fields_by_key.get(ref.field_key)
        if field is None:
            raise _CompileError(
                CompilerIssueCode.UNKNOWN_FIELD,
                f"unknown select field {ref.field_key!r}",
                field_key=ref.field_key,
            )
        _assert_ident(field.physical_column.column_name, "column")
        parts.append(
            f"{alias}.{_q(field.physical_column.column_name)} AS {_q(ref.field_key)}"
        )
    for agg in plan.aggregations:
        field = fields_by_key.get(agg.field_key)
        if field is None:
            raise _CompileError(
                CompilerIssueCode.UNKNOWN_FIELD,
                f"unknown aggregation field {agg.field_key!r}",
                field_key=agg.field_key,
            )
        function = AggregationFunction(str(agg.function))
        if function not in _AGG_SQL:
            raise _CompileError(
                CompilerIssueCode.UNSUPPORTED_AGGREGATION,
                f"unsupported aggregation {agg.function!r}",
                field_key=agg.field_key,
            )
        _assert_ident(field.physical_column.column_name, "column")
        out_alias = agg.alias or f"{function.value.lower()}_{agg.field_key}"
        _assert_ident(out_alias, "alias")
        parts.append(
            f"{_AGG_SQL[function]}({alias}.{_q(field.physical_column.column_name)}) "
            f"AS {_q(out_alias)}"
        )
    if not parts:
        raise _CompileError(
            CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
            "SELECT list is empty",
        )
    # Fail closed: never emit SELECT *.
    if any(p.strip() == "*" or p.strip().endswith(".*") for p in parts):
        raise _CompileError(
            CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
            "SELECT * is forbidden",
        )
    return ", ".join(parts)


def _compile_where(
    filters: tuple[ValidatedFilterPredicate, ...],
    fields_by_key: dict[str, ResolvedLogicalField],
    alias: str,
    binds: _BindBuilder,
) -> str:
    if not filters:
        return ""
    clauses: list[str] = []
    for predicate in filters:
        field = fields_by_key.get(predicate.field_key)
        if field is None:
            raise _CompileError(
                CompilerIssueCode.UNKNOWN_FIELD,
                f"unknown filter field {predicate.field_key!r}",
                field_key=predicate.field_key,
            )
        _assert_ident(field.physical_column.column_name, "column")
        col = f"{alias}.{_q(field.physical_column.column_name)}"
        operator = FilterOperator(str(predicate.operator))
        param_type = _bind_type(field.data_type)

        if operator is FilterOperator.IS_NULL:
            clauses.append(f"{col} IS NULL")
            continue
        if operator is FilterOperator.IS_NOT_NULL:
            clauses.append(f"{col} IS NOT NULL")
            continue
        if operator is FilterOperator.IN:
            values = _as_sequence(predicate.value)
            names = [
                binds.add(item, param_type=param_type) for item in values
            ]
            clauses.append(f"{col} IN ({', '.join(':' + n for n in names)})")
            continue
        if operator is FilterOperator.NOT_IN:
            values = _as_sequence(predicate.value)
            names = [
                binds.add(item, param_type=param_type) for item in values
            ]
            clauses.append(f"{col} NOT IN ({', '.join(':' + n for n in names)})")
            continue
        if operator is FilterOperator.BETWEEN:
            values = _as_sequence(predicate.value)
            if len(values) != 2:
                raise _CompileError(
                    CompilerIssueCode.UNSUPPORTED_OPERATOR,
                    "BETWEEN requires exactly two bind values",
                    field_key=predicate.field_key,
                )
            lo = binds.add(values[0], param_type=param_type)
            hi = binds.add(values[1], param_type=param_type)
            clauses.append(f"{col} BETWEEN :{lo} AND :{hi}")
            continue
        if operator in _OP_SQL:
            name = binds.add(predicate.value, param_type=param_type)
            clauses.append(f"{col} {_OP_SQL[operator]} :{name}")
            continue
        raise _CompileError(
            CompilerIssueCode.UNSUPPORTED_OPERATOR,
            f"unsupported filter operator {operator.value}",
            field_key=predicate.field_key,
        )
    return "WHERE " + " AND ".join(clauses)


def _compile_group_by(
    group_by: tuple[ValidatedFieldRef, ...],
    fields_by_key: dict[str, ResolvedLogicalField],
    alias: str,
) -> str:
    if not group_by:
        return ""
    parts: list[str] = []
    for ref in group_by:
        field = fields_by_key.get(ref.field_key)
        if field is None:
            raise _CompileError(
                CompilerIssueCode.UNKNOWN_FIELD,
                f"unknown group_by field {ref.field_key!r}",
                field_key=ref.field_key,
            )
        _assert_ident(field.physical_column.column_name, "column")
        parts.append(f"{alias}.{_q(field.physical_column.column_name)}")
    return "GROUP BY " + ", ".join(parts)


def _compile_order_by(
    sort: tuple[ValidatedSortSpec, ...],
    fields_by_key: dict[str, ResolvedLogicalField],
    alias: str,
) -> str:
    if not sort:
        return ""
    parts: list[str] = []
    for spec in sort:
        field = fields_by_key.get(spec.field_key)
        if field is None:
            raise _CompileError(
                CompilerIssueCode.UNKNOWN_FIELD,
                f"unknown sort field {spec.field_key!r}",
                field_key=spec.field_key,
            )
        _assert_ident(field.physical_column.column_name, "column")
        direction = SortDirection(str(spec.direction))
        parts.append(
            f"{alias}.{_q(field.physical_column.column_name)} {direction.value}"
        )
    return "ORDER BY " + ", ".join(parts)


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    raise _CompileError(
        CompilerIssueCode.UNSUPPORTED_OPERATOR,
        "expected sequence filter value for IN/BETWEEN",
    )


def _bind_type(data_type: str) -> str:
    logical = normalize_logical_data_type(data_type)
    if logical is LogicalDataType.INTEGER:
        return "integer"
    if logical is LogicalDataType.NUMBER:
        return "decimal"
    if logical is LogicalDataType.BOOLEAN:
        return "boolean"
    if logical is LogicalDataType.DATE:
        return "date"
    if logical is LogicalDataType.DATETIME:
        return "datetime"
    return "string"


def _assert_ident(name: str, kind: str) -> None:
    if not isinstance(name, str) or not _IDENT_RE.fullmatch(name):
        raise _CompileError(
            CompilerIssueCode.INVALID_IDENTIFIER,
            f"invalid Oracle {kind} identifier {name!r}",
        )


def _q(name: str) -> str:
    """Double-quote a validated Oracle identifier (no value concatenation)."""
    _assert_ident(name, "identifier")
    return f'"{name}"'


def _map_plan_status(status: PlanValidationStatus | str) -> CompilerStatus:
    text = str(status)
    if text == PlanValidationStatus.VALID:
        return CompilerStatus.VALID
    if text == PlanValidationStatus.NOT_CONFIGURED:
        return CompilerStatus.NOT_CONFIGURED
    if text == PlanValidationStatus.STALE:
        return CompilerStatus.STALE
    return CompilerStatus.INVALID


def _plan_gate_issues(validated: ValidatedLogicalPlan) -> list[CompilerIssue]:
    status = str(validated.status)
    if status == PlanValidationStatus.NOT_CONFIGURED:
        return [
            CompilerIssue(
                code=CompilerIssueCode.NOT_CONFIGURED,
                message="semantic mapping is NOT_CONFIGURED for source",
            )
        ]
    if status == PlanValidationStatus.STALE:
        return [
            CompilerIssue(
                code=CompilerIssueCode.STALE_MAPPING,
                message="semantic mapping is STALE relative to active catalog",
            )
        ]
    if validated.issues:
        first = validated.issues[0]
        return [
            CompilerIssue(
                code=CompilerIssueCode.PLAN_INVALID,
                message=f"plan validation failed: {first.message}",
                field_key=first.field_key,
            )
        ]
    return [
        CompilerIssue(
            code=CompilerIssueCode.PLAN_INVALID,
            message="plan validation failed",
        )
    ]


def _failure(
    *,
    plan: StructuredQueryPlan,
    validated: ValidatedLogicalPlan,
    status: CompilerStatus,
    issues: list[CompilerIssue],
    sql_safety: SqlSafetyReport | None = None,
) -> CompiledQueryResult:
    return CompiledQueryResult(
        preview_only=True,
        validation_only=True,
        approved=False,
        executable=False,
        status=status,
        compiler_version=COMPILER_VERSION,
        source_name=validated.source_name or plan.source_name,
        catalog_revision_id=validated.catalog_revision_id,
        schema_fingerprint=validated.schema_fingerprint,
        mapping_version=validated.mapping_version,
        resource_key=validated.resource_key or plan.resource_key,
        sql_text=None,
        bind_parameters={},
        sql_safety=sql_safety,
        issues=tuple(issues),
    )


__all__ = [
    "compile_structured_query_plan",
]
