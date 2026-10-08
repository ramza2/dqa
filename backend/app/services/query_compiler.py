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
from app.domain.semantic_resource import SemanticMappingStatus
from app.schemas.semantic_resource import (
    ResolvedLogicalField,
    ResolvedLogicalResource,
    SemanticResolutionResult,
)
from app.schemas.structured_query_plan import (
    StructuredQueryPlan,
    ValidatedFieldRef,
    ValidatedFilterPredicate,
    ValidatedLogicalPlan,
    ValidatedSortSpec,
)
from app.schemas.sql_safety import SqlSafetyReport
from app.services.catalog_query import (
    ResolvedActiveRevision,
    _doc_list,
    _map_column,
    _map_table,
    resolve_active_revision,
)
from app.services.semantic_resource import (
    SemanticResourceRegistry,
    resolve_semantic_resources,
)
from app.services.sql_safety import validate_sql_safety
from app.services.structured_query_plan import validate_structured_query_plan

_IDENT_RE = re.compile(ORACLE_IDENT_PATTERN)
_ALIAS_RE = re.compile(r"^t\d+$")
_OUTER_QUERY_ALIAS = "q"

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
    # ValidatedLogicalPlan carries logical identities only — never trusted alone.
    semantic = resolve_semantic_resources(
        session, plan.source_name, registry=registry
    )
    drift_issue = _check_snapshot_consistency(validated, semantic)
    if drift_issue is not None:
        return _failure(
            plan=plan,
            validated=validated,
            status=CompilerStatus.INVALID,
            issues=[drift_issue],
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

    try:
        active = resolve_active_revision(session, validated.source_name)
        spelling = _CatalogSpellingIndex.from_active(active)
        sql_text, binds, param_schema = _compile_oracle_select(
            validated, resource, semantic.resources, spelling
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


def _check_snapshot_consistency(
    validated: ValidatedLogicalPlan,
    semantic: SemanticResolutionResult,
) -> CompilerIssue | None:
    """Require second resolve VALID and identical provenance to the validated plan."""
    if str(semantic.status) != SemanticMappingStatus.VALID:
        return CompilerIssue(
            code=CompilerIssueCode.SNAPSHOT_DRIFT,
            message=(
                f"semantic re-resolution status {semantic.status!r} is not VALID "
                "after plan validation"
            ),
        )
    if (
        semantic.source_name != validated.source_name
        or semantic.catalog_revision_id != validated.catalog_revision_id
        or semantic.schema_fingerprint != validated.schema_fingerprint
        or semantic.mapping_version != validated.mapping_version
    ):
        return CompilerIssue(
            code=CompilerIssueCode.SNAPSHOT_DRIFT,
            message=(
                "semantic re-resolution drifted from validated plan "
                "(source/revision/fingerprint/mapping_version mismatch); "
                "no SQL emitted"
            ),
        )
    return None


@dataclass(frozen=True)
class _CatalogSpellingIndex:
    """Authoritative Catalog identifier spellings (exact case from snapshot)."""

    # casefold(schema, table) -> (schema, table) exact
    tables: dict[tuple[str, str], tuple[str, str]]
    # casefold(schema, table, column) -> column exact
    columns: dict[tuple[str, str, str], str]

    @classmethod
    def from_active(cls, active: ResolvedActiveRevision) -> _CatalogSpellingIndex:
        tables: dict[tuple[str, str], tuple[str, str]] = {}
        for raw in _doc_list(active.revision.tables_json, "tables"):
            item = _map_table(raw, {})
            key = (item.schema_name.casefold(), item.name.casefold())
            if key in tables and tables[key] != (item.schema_name, item.name):
                raise _CompileError(
                    CompilerIssueCode.INVALID_IDENTIFIER,
                    f"ambiguous Catalog table spelling for {item.schema_name}.{item.name}",
                )
            tables[key] = (item.schema_name, item.name)

        columns: dict[tuple[str, str, str], str] = {}
        for raw in _doc_list(active.revision.columns_json, "columns"):
            item = _map_column(raw)
            schema = item.schema_name or ""
            key = (schema.casefold(), item.table_name.casefold(), item.name.casefold())
            if key in columns and columns[key] != item.name:
                raise _CompileError(
                    CompilerIssueCode.INVALID_IDENTIFIER,
                    (
                        f"ambiguous Catalog column spelling for "
                        f"{schema}.{item.table_name}.{item.name}"
                    ),
                )
            columns[key] = item.name
        return cls(tables=tables, columns=columns)

    def table(self, schema_name: str, table_name: str) -> tuple[str, str]:
        key = (schema_name.casefold(), table_name.casefold())
        exact = self.tables.get(key)
        if exact is None:
            raise _CompileError(
                CompilerIssueCode.INVALID_IDENTIFIER,
                f"Catalog table not found for {schema_name}.{table_name}",
            )
        return exact

    def column(self, schema_name: str, table_name: str, column_name: str) -> str:
        schema_exact, table_exact = self.table(schema_name, table_name)
        key = (
            schema_exact.casefold(),
            table_exact.casefold(),
            column_name.casefold(),
        )
        exact = self.columns.get(key)
        if exact is None:
            raise _CompileError(
                CompilerIssueCode.INVALID_IDENTIFIER,
                f"Catalog column not found for {schema_name}.{table_name}.{column_name}",
            )
        return exact


def _compile_oracle_select(
    plan: ValidatedLogicalPlan,
    resource: ResolvedLogicalResource,
    all_resources: list[ResolvedLogicalResource],
    spelling: _CatalogSpellingIndex,
) -> tuple[str, dict[str, Any], list[QueryTemplateParameter]]:
    fields_by_key = {f.field_key: f for f in resource.fields}
    relationships_by_key = {r.relationship_key: r for r in resource.relationships}
    resources_by_key = {r.resource_key: r for r in all_resources}

    projection_aliases = _unique_projection_aliases(plan)
    primary_alias = "t0"
    primary_schema, primary_table = spelling.table(
        resource.physical_table.schema_name,
        resource.physical_table.table_name,
    )
    _assert_ident(primary_schema, "schema")
    _assert_ident(primary_table, "table")

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
        target_schema, target_table = spelling.table(
            target.physical_table.schema_name,
            target.physical_table.table_name,
        )
        _assert_ident(target_schema, "schema")
        _assert_ident(target_table, "table")
        on_parts: list[str] = []
        for mapping in rel.catalog_fk.column_mappings:
            src_col = spelling.column(
                primary_schema, primary_table, mapping.source_column
            )
            tgt_col = spelling.column(
                target_schema, target_table, mapping.target_column
            )
            _assert_ident(src_col, "column")
            _assert_ident(tgt_col, "column")
            on_parts.append(
                f"{primary_alias}.{_q(src_col)} = {alias}.{_q(tgt_col)}"
            )
        if not on_parts:
            raise _CompileError(
                CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
                f"relationship {rel_key!r} has empty FK column mappings",
            )
        join_clauses.append(
            "INNER JOIN "
            f"{_q(target_schema)}.{_q(target_table)} {alias} "
            f"ON {' AND '.join(on_parts)}"
        )

    binds = _BindBuilder()
    select_sql = _compile_select_list(
        plan, fields_by_key, primary_alias, spelling, primary_schema, primary_table
    )
    from_sql = f"FROM {_q(primary_schema)}.{_q(primary_table)} {primary_alias}"
    join_sql = " ".join(join_clauses)
    where_sql = _compile_where(
        plan.filters,
        fields_by_key,
        primary_alias,
        binds,
        spelling,
        primary_schema,
        primary_table,
    )
    group_sql = _compile_group_by(
        plan.group_by,
        fields_by_key,
        primary_alias,
        spelling,
        primary_schema,
        primary_table,
    )
    order_sql = _compile_order_by(
        plan.sort,
        fields_by_key,
        primary_alias,
        spelling,
        primary_schema,
        primary_table,
    )
    if plan.limit is None:
        raise _CompileError(
            CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
            "validated plan is missing bounded limit",
        )
    limit_name = binds.add_limit(int(plan.limit))

    inner_parts = [f"SELECT {select_sql}", from_sql]
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
        f"{_OUTER_QUERY_ALIAS}.{_q(item)}" for item in projection_aliases
    )
    sql_text = (
        f"SELECT {outer_select} FROM ({inner_sql}) {_OUTER_QUERY_ALIAS} "
        f"WHERE ROWNUM <= :{limit_name}"
    )
    return sql_text, binds.parameters, binds.schema


def _unique_projection_aliases(plan: ValidatedLogicalPlan) -> list[str]:
    """Return ordered projection aliases; reject collisions fail-closed."""
    aliases: list[str] = []
    seen: set[str] = set()
    for ref in plan.select:
        _assert_ident(ref.field_key, "alias")
        if ref.field_key == _OUTER_QUERY_ALIAS:
            raise _CompileError(
                CompilerIssueCode.ALIAS_COLLISION,
                f"projection alias {ref.field_key!r} collides with outer query alias",
                field_key=ref.field_key,
            )
        if ref.field_key in seen:
            raise _CompileError(
                CompilerIssueCode.ALIAS_COLLISION,
                f"duplicate projection alias {ref.field_key!r}",
                field_key=ref.field_key,
            )
        seen.add(ref.field_key)
        aliases.append(ref.field_key)
    for agg in plan.aggregations:
        function = AggregationFunction(str(agg.function))
        out_alias = agg.alias or f"{function.value.lower()}_{agg.field_key}"
        _assert_ident(out_alias, "alias")
        if out_alias == _OUTER_QUERY_ALIAS:
            raise _CompileError(
                CompilerIssueCode.ALIAS_COLLISION,
                f"aggregation alias {out_alias!r} collides with outer query alias",
                field_key=agg.field_key,
            )
        if out_alias in seen:
            raise _CompileError(
                CompilerIssueCode.ALIAS_COLLISION,
                f"projection alias collision on {out_alias!r}",
                field_key=agg.field_key,
            )
        seen.add(out_alias)
        aliases.append(out_alias)
    if not aliases:
        raise _CompileError(
            CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
            "SELECT list is empty",
        )
    return aliases


def _physical_column(
    field: ResolvedLogicalField,
    spelling: _CatalogSpellingIndex,
    schema_name: str,
    table_name: str,
) -> str:
    """Resolve mapping column name to authoritative Catalog spelling."""
    return spelling.column(
        field.physical_column.schema_name or schema_name,
        field.physical_column.table_name or table_name,
        field.physical_column.column_name,
    )


def _compile_select_list(
    plan: ValidatedLogicalPlan,
    fields_by_key: dict[str, ResolvedLogicalField],
    alias: str,
    spelling: _CatalogSpellingIndex,
    schema_name: str,
    table_name: str,
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
        col = _physical_column(field, spelling, schema_name, table_name)
        _assert_ident(col, "column")
        parts.append(f"{alias}.{_q(col)} AS {_q(ref.field_key)}")
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
        col = _physical_column(field, spelling, schema_name, table_name)
        _assert_ident(col, "column")
        out_alias = agg.alias or f"{function.value.lower()}_{agg.field_key}"
        _assert_ident(out_alias, "alias")
        parts.append(
            f"{_AGG_SQL[function]}({alias}.{_q(col)}) AS {_q(out_alias)}"
        )
    if not parts:
        raise _CompileError(
            CompilerIssueCode.UNSUPPORTED_SQL_SHAPE,
            "SELECT list is empty",
        )
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
    spelling: _CatalogSpellingIndex,
    schema_name: str,
    table_name: str,
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
        col_name = _physical_column(field, spelling, schema_name, table_name)
        _assert_ident(col_name, "column")
        col = f"{alias}.{_q(col_name)}"
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
            names = [binds.add(item, param_type=param_type) for item in values]
            clauses.append(f"{col} IN ({', '.join(':' + n for n in names)})")
            continue
        if operator is FilterOperator.NOT_IN:
            values = _as_sequence(predicate.value)
            names = [binds.add(item, param_type=param_type) for item in values]
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
    spelling: _CatalogSpellingIndex,
    schema_name: str,
    table_name: str,
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
        col = _physical_column(field, spelling, schema_name, table_name)
        _assert_ident(col, "column")
        parts.append(f"{alias}.{_q(col)}")
    return "GROUP BY " + ", ".join(parts)


def _compile_order_by(
    sort: tuple[ValidatedSortSpec, ...],
    fields_by_key: dict[str, ResolvedLogicalField],
    alias: str,
    spelling: _CatalogSpellingIndex,
    schema_name: str,
    table_name: str,
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
        col = _physical_column(field, spelling, schema_name, table_name)
        _assert_ident(col, "column")
        direction = SortDirection(str(spec.direction))
        parts.append(f"{alias}.{_q(col)} {direction.value}")
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
