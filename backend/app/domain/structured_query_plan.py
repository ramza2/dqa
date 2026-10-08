"""Structured Query Plan domain contracts (Phase 29-B).

Validation-only logical plans for future Dynamic Query. No SQL compilation,
execution tokens, or approved-production authority.
"""

from __future__ import annotations

from enum import StrEnum

PLAN_FORMAT_VERSION = "1.0.0"

# Hard bounds — oversized plans fail closed at contract + validator layers.
MAX_SELECT_FIELDS = 32
MAX_FILTERS = 16
MAX_SORT_SPECS = 8
MAX_GROUP_BY_FIELDS = 8
MAX_AGGREGATIONS = 8
MAX_RELATIONSHIPS = 4
MAX_IN_LIST_SIZE = 50
MAX_LIMIT = 1000
MIN_LIMIT = 1
MAX_STRING_VALUE_LENGTH = 512


class FilterOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"
    IN = "IN"
    NOT_IN = "NOT_IN"
    BETWEEN = "BETWEEN"
    LIKE = "LIKE"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"


class SortDirection(StrEnum):
    ASC = "ASC"
    DESC = "DESC"


class AggregationFunction(StrEnum):
    COUNT = "COUNT"
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class LogicalDataType(StrEnum):
    """Normalized logical types used for operator/value validation."""

    INTEGER = "integer"
    NUMBER = "number"
    STRING = "string"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"


class PlanValidationStatus(StrEnum):
    """Outcome of Structured Query Plan validation."""

    VALID = "VALID"
    INVALID = "INVALID"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    STALE = "STALE"


class PlanIssueCode(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    SEMANTIC_MAPPING_INVALID = "SEMANTIC_MAPPING_INVALID"
    STALE_MAPPING = "STALE_MAPPING"
    CROSS_SOURCE = "CROSS_SOURCE"
    UNKNOWN_RESOURCE = "UNKNOWN_RESOURCE"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    UNKNOWN_RELATIONSHIP = "UNKNOWN_RELATIONSHIP"
    DUPLICATE_RELATIONSHIP = "DUPLICATE_RELATIONSHIP"
    MISSING_CAPABILITY = "MISSING_CAPABILITY"
    UNSUPPORTED_OPERATOR = "UNSUPPORTED_OPERATOR"
    INVALID_FILTER_VALUE = "INVALID_FILTER_VALUE"
    UNSUPPORTED_AGGREGATION = "UNSUPPORTED_AGGREGATION"
    INVALID_GROUPING = "INVALID_GROUPING"
    AMBIGUOUS_JOIN = "AMBIGUOUS_JOIN"
    COMPLEXITY_EXCEEDED = "COMPLEXITY_EXCEEDED"
    UNSUPPORTED_PLAN_VERSION = "UNSUPPORTED_PLAN_VERSION"
    FORBIDDEN_INPUT = "FORBIDDEN_INPUT"


# Operators permitted per normalized logical data type.
OPERATORS_BY_TYPE: dict[LogicalDataType, frozenset[FilterOperator]] = {
    LogicalDataType.INTEGER: frozenset(
        {
            FilterOperator.EQ,
            FilterOperator.NE,
            FilterOperator.LT,
            FilterOperator.LE,
            FilterOperator.GT,
            FilterOperator.GE,
            FilterOperator.IN,
            FilterOperator.NOT_IN,
            FilterOperator.BETWEEN,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        }
    ),
    LogicalDataType.NUMBER: frozenset(
        {
            FilterOperator.EQ,
            FilterOperator.NE,
            FilterOperator.LT,
            FilterOperator.LE,
            FilterOperator.GT,
            FilterOperator.GE,
            FilterOperator.IN,
            FilterOperator.NOT_IN,
            FilterOperator.BETWEEN,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        }
    ),
    LogicalDataType.STRING: frozenset(
        {
            FilterOperator.EQ,
            FilterOperator.NE,
            FilterOperator.IN,
            FilterOperator.NOT_IN,
            FilterOperator.LIKE,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        }
    ),
    LogicalDataType.BOOLEAN: frozenset(
        {
            FilterOperator.EQ,
            FilterOperator.NE,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        }
    ),
    LogicalDataType.DATE: frozenset(
        {
            FilterOperator.EQ,
            FilterOperator.NE,
            FilterOperator.LT,
            FilterOperator.LE,
            FilterOperator.GT,
            FilterOperator.GE,
            FilterOperator.BETWEEN,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        }
    ),
    LogicalDataType.DATETIME: frozenset(
        {
            FilterOperator.EQ,
            FilterOperator.NE,
            FilterOperator.LT,
            FilterOperator.LE,
            FilterOperator.GT,
            FilterOperator.GE,
            FilterOperator.BETWEEN,
            FilterOperator.IS_NULL,
            FilterOperator.IS_NOT_NULL,
        }
    ),
}

NUMERIC_AGGREGATIONS: frozenset[AggregationFunction] = frozenset(
    {
        AggregationFunction.SUM,
        AggregationFunction.AVG,
    }
)

NULLARY_OPERATORS: frozenset[FilterOperator] = frozenset(
    {
        FilterOperator.IS_NULL,
        FilterOperator.IS_NOT_NULL,
    }
)

LIST_OPERATORS: frozenset[FilterOperator] = frozenset(
    {
        FilterOperator.IN,
        FilterOperator.NOT_IN,
    }
)


def normalize_logical_data_type(raw: str) -> LogicalDataType | None:
    """Map declared field data_type strings to a normalized logical type."""
    text = (raw or "").strip().casefold()
    aliases: dict[str, LogicalDataType] = {
        "integer": LogicalDataType.INTEGER,
        "int": LogicalDataType.INTEGER,
        "long": LogicalDataType.INTEGER,
        "number": LogicalDataType.NUMBER,
        "float": LogicalDataType.NUMBER,
        "double": LogicalDataType.NUMBER,
        "decimal": LogicalDataType.NUMBER,
        "string": LogicalDataType.STRING,
        "str": LogicalDataType.STRING,
        "text": LogicalDataType.STRING,
        "varchar": LogicalDataType.STRING,
        "boolean": LogicalDataType.BOOLEAN,
        "bool": LogicalDataType.BOOLEAN,
        "date": LogicalDataType.DATE,
        "datetime": LogicalDataType.DATETIME,
        "timestamp": LogicalDataType.DATETIME,
    }
    return aliases.get(text)


__all__ = [
    "MAX_AGGREGATIONS",
    "MAX_FILTERS",
    "MAX_GROUP_BY_FIELDS",
    "MAX_IN_LIST_SIZE",
    "MAX_LIMIT",
    "MAX_RELATIONSHIPS",
    "MAX_SELECT_FIELDS",
    "MAX_SORT_SPECS",
    "MAX_STRING_VALUE_LENGTH",
    "MIN_LIMIT",
    "NUMERIC_AGGREGATIONS",
    "NULLARY_OPERATORS",
    "LIST_OPERATORS",
    "OPERATORS_BY_TYPE",
    "PLAN_FORMAT_VERSION",
    "AggregationFunction",
    "FilterOperator",
    "LogicalDataType",
    "PlanIssueCode",
    "PlanValidationStatus",
    "SortDirection",
    "normalize_logical_data_type",
]
