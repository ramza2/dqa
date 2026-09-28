"""Deterministic Query Template parameter value validation.

Reusable by Parameter Extraction and future SQL Execution Gate.
Does not call LLMs, databases, or mutate templates.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.parameter_extraction import (
    ISSUE_ENUM_NOT_ALLOWED,
    ISSUE_MAX_ITEMS_VIOLATION,
    ISSUE_MAX_VIOLATION,
    ISSUE_MIN_ITEMS_VIOLATION,
    ISSUE_MIN_VIOLATION,
    ISSUE_MISSING_REQUIRED,
    ISSUE_PATTERN_MISMATCH,
    ISSUE_TYPE_MISMATCH,
    ISSUE_UNRESOLVED,
    ParameterExtractionIssueView,
)
from app.schemas.query_template import QueryTemplateParameter


@dataclass
class ParameterValidationResult:
    """Outcome of deterministic parameter validation."""

    resolved_parameters: dict[str, Any] = field(default_factory=dict)
    issues: list[ParameterExtractionIssueView] = field(default_factory=list)

    @property
    def needs_clarification(self) -> bool:
        return len(self.issues) > 0


def validate_parameter_values(
    parameter_schema: list[QueryTemplateParameter],
    extracted_values: dict[str, Any],
    unresolved_names: set[str] | list[str],
) -> ParameterValidationResult:
    """Validate extracted values against declared parameter schema.

    Does not log or embed actual parameter values in issue messages.
    """
    unresolved = set(unresolved_names)
    result = ParameterValidationResult()
    declared = {param.name: param for param in parameter_schema}

    for name, param in declared.items():
        if name in unresolved:
            result.issues.append(
                ParameterExtractionIssueView(
                    parameter_name=name,
                    code=ISSUE_UNRESOLVED,
                    message="parameter value is unresolved and requires clarification",
                )
            )
            continue

        if name in extracted_values:
            issue = _validate_one(param, extracted_values[name])
            if issue is not None:
                result.issues.append(issue)
            else:
                result.resolved_parameters[name] = extracted_values[name]
            continue

        if param.default is not None:
            # Defaults already passed QueryTemplateParameter schema validation.
            result.resolved_parameters[name] = param.default
            continue

        if param.required:
            result.issues.append(
                ParameterExtractionIssueView(
                    parameter_name=name,
                    code=ISSUE_MISSING_REQUIRED,
                    message="required parameter is missing",
                )
            )
        # Optional + no default + not extracted => leave unset (no issue).

    return result


def _validate_one(
    param: QueryTemplateParameter, value: Any
) -> ParameterExtractionIssueView | None:
    param_type = param.type

    if param_type == "string":
        if not isinstance(value, str):
            return _issue(param.name, ISSUE_TYPE_MISMATCH, "parameter must be a string")
        if param.pattern is not None and re.fullmatch(param.pattern, value) is None:
            return _issue(
                param.name,
                ISSUE_PATTERN_MISMATCH,
                "parameter value does not match the required pattern",
            )
        return None

    if param_type == "integer":
        if not _is_int(value):
            return _issue(param.name, ISSUE_TYPE_MISMATCH, "parameter must be an integer")
        return _check_min_max(param, value)

    if param_type == "decimal":
        if not _is_number(value):
            return _issue(param.name, ISSUE_TYPE_MISMATCH, "parameter must be a number")
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return _issue(
                param.name,
                ISSUE_TYPE_MISMATCH,
                "parameter must be a finite number",
            )
        try:
            as_decimal = Decimal(str(value))
        except (InvalidOperation, ValueError):
            return _issue(
                param.name,
                ISSUE_TYPE_MISMATCH,
                "parameter must be a finite number",
            )
        return _check_min_max(param, as_decimal)

    if param_type == "boolean":
        if not isinstance(value, bool):
            return _issue(param.name, ISSUE_TYPE_MISMATCH, "parameter must be a boolean")
        return None

    if param_type == "date":
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return _issue(
                param.name,
                ISSUE_TYPE_MISMATCH,
                "parameter must be an ISO date string",
            )
        try:
            date.fromisoformat(value)
        except ValueError:
            return _issue(
                param.name,
                ISSUE_TYPE_MISMATCH,
                "parameter must be an ISO date string",
            )
        return None

    if param_type == "datetime":
        if not isinstance(value, str):
            return _issue(
                param.name,
                ISSUE_TYPE_MISMATCH,
                "parameter must be an ISO datetime string",
            )
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return _issue(
                param.name,
                ISSUE_TYPE_MISMATCH,
                "parameter must be an ISO datetime string",
            )
        return None

    if param_type == "enum":
        allowed = param.allowed_values or []
        if not any(_values_equal(value, item) for item in allowed):
            return _issue(
                param.name,
                ISSUE_ENUM_NOT_ALLOWED,
                "parameter value is not in the allowed set",
            )
        return None

    if param_type == "string_list":
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            return _issue(
                param.name,
                ISSUE_TYPE_MISMATCH,
                "parameter must be a list of strings",
            )
        return _check_list_bounds(param, value)

    if param_type == "integer_list":
        if not isinstance(value, list) or not all(_is_int(item) for item in value):
            return _issue(
                param.name,
                ISSUE_TYPE_MISMATCH,
                "parameter must be a list of integers",
            )
        return _check_list_bounds(param, value)

    return _issue(param.name, ISSUE_TYPE_MISMATCH, "unsupported parameter type")


def _check_min_max(
    param: QueryTemplateParameter, value: Any
) -> ParameterExtractionIssueView | None:
    if param.min is not None and value < param.min:
        return _issue(
            param.name,
            ISSUE_MIN_VIOLATION,
            "parameter is below the minimum allowed value",
        )
    if param.max is not None and value > param.max:
        return _issue(
            param.name,
            ISSUE_MAX_VIOLATION,
            "parameter is above the maximum allowed value",
        )
    return None


def _check_list_bounds(
    param: QueryTemplateParameter, value: list[Any]
) -> ParameterExtractionIssueView | None:
    length = len(value)
    if param.min_items is not None and length < param.min_items:
        return _issue(
            param.name,
            ISSUE_MIN_ITEMS_VIOLATION,
            "parameter list has fewer items than allowed",
        )
    if param.max_items is not None and length > param.max_items:
        return _issue(
            param.name,
            ISSUE_MAX_ITEMS_VIOLATION,
            "parameter list has more items than allowed",
        )
    return None


def _issue(name: str, code: str, message: str) -> ParameterExtractionIssueView:
    return ParameterExtractionIssueView(parameter_name=name, code=code, message=message)


def _values_equal(left: Any, right: Any) -> bool:
    return left == right and type(left) is type(right)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float, Decimal))
