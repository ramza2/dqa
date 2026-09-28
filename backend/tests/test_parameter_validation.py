"""Focused deterministic parameter validation tests (no LLM / no DB)."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

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
)
from app.schemas.query_template import QueryTemplateParameter
from app.services.parameter_validation import validate_parameter_values


def _p(**overrides: object) -> QueryTemplateParameter:
    body: dict[str, object] = {
        "name": "value",
        "type": "string",
        "required": True,
    }
    body.update(overrides)
    return QueryTemplateParameter.model_validate(body)


def _codes(result) -> set[str]:
    return {issue.code for issue in result.issues}


def test_string_valid_and_pattern() -> None:
    param = _p(name="code", type="string", pattern=r"^[A-Z]{2}$")
    ok = validate_parameter_values([param], {"code": "AB"}, [])
    assert ok.needs_clarification is False
    assert ok.resolved_parameters == {"code": "AB"}

    bad_type = validate_parameter_values([param], {"code": 12}, [])
    assert ISSUE_TYPE_MISMATCH in _codes(bad_type)

    bad_pattern = validate_parameter_values([param], {"code": "ab"}, [])
    assert ISSUE_PATTERN_MISMATCH in _codes(bad_pattern)
    assert "ab" not in bad_pattern.issues[0].message


def test_integer_rejects_string_bool_and_bounds() -> None:
    param = _p(name="n", type="integer", min=1, max=10)
    assert validate_parameter_values([param], {"n": 5}, []).resolved_parameters == {"n": 5}
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([param], {"n": "10"}, [])
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([param], {"n": True}, [])
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([param], {"n": 10.0}, [])
    )
    assert ISSUE_MIN_VIOLATION in _codes(validate_parameter_values([param], {"n": 0}, []))
    assert ISSUE_MAX_VIOLATION in _codes(validate_parameter_values([param], {"n": 11}, []))


def test_decimal_rejects_string_nan_inf() -> None:
    param = _p(name="amt", type="decimal", min=0, max=100)
    assert validate_parameter_values([param], {"amt": 1}, []).needs_clarification is False
    assert validate_parameter_values([param], {"amt": 1.5}, []).needs_clarification is False
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([param], {"amt": "1.5"}, [])
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([param], {"amt": math.nan}, [])
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([param], {"amt": math.inf}, [])
    )


def test_boolean_strict() -> None:
    param = _p(name="flag", type="boolean")
    assert validate_parameter_values([param], {"flag": True}, []).resolved_parameters == {
        "flag": True
    }
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([param], {"flag": "true"}, [])
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([param], {"flag": 1}, [])
    )


def test_date_and_datetime() -> None:
    date_param = _p(name="d", type="date")
    assert validate_parameter_values([date_param], {"d": "2026-09-01"}, []).needs_clarification is False
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([date_param], {"d": "2026-09-01T10:00:00"}, [])
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([date_param], {"d": "not-a-date"}, [])
    )

    dt_param = _p(name="ts", type="datetime")
    assert (
        validate_parameter_values(
            [dt_param], {"ts": "2026-09-01T10:00:00"}, []
        ).needs_clarification
        is False
    )
    assert (
        validate_parameter_values(
            [dt_param], {"ts": "2026-09-01T10:00:00+09:00"}, []
        ).needs_clarification
        is False
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([dt_param], {"ts": "2026-09-01"}, [])
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([dt_param], {"ts": "bad"}, [])
    )


def test_parameter_default_constraints_fail_closed() -> None:
    with pytest.raises(ValidationError):
        _p(name="code", type="string", pattern=r"^[A-Z]{2}$", default="ab")
    with pytest.raises(ValidationError):
        _p(name="n", type="integer", min=1, max=10, default=0)
    with pytest.raises(ValidationError):
        _p(name="n", type="integer", min=1, max=10, default=11)
    with pytest.raises(ValidationError):
        _p(name="amt", type="decimal", default=math.nan)
    with pytest.raises(ValidationError):
        _p(name="amt", type="decimal", default=math.inf)
    with pytest.raises(ValidationError):
        _p(name="amt", type="decimal", min=0, max=10, default=-1)
    with pytest.raises(ValidationError):
        _p(name="amt", type="decimal", min=0, max=10, default=11)
    with pytest.raises(ValidationError):
        _p(name="tags", type="string_list", min_items=1, default=[])
    with pytest.raises(ValidationError):
        _p(name="tags", type="string_list", max_items=1, default=["a", "b"])
    with pytest.raises(ValidationError):
        _p(name="ids", type="integer_list", min_items=2, default=[1])
    with pytest.raises(ValidationError):
        _p(name="ids", type="integer_list", max_items=1, default=[1, 2])
    with pytest.raises(ValidationError):
        _p(name="ts", type="datetime", default="2026-09-01")


def test_parameter_valid_defaults_regression() -> None:
    assert _p(name="code", type="string", pattern=r"^[A-Z]{2}$", default="AB").default == "AB"
    assert _p(name="n", type="integer", min=1, max=10, default=5).default == 5
    assert _p(name="amt", type="decimal", min=0, max=10, default=1.5).default == 1.5
    assert _p(name="amt", type="decimal", default=2).default == 2
    assert _p(name="tags", type="string_list", min_items=1, max_items=3, default=["a"]).default == [
        "a"
    ]
    assert _p(name="ids", type="integer_list", min_items=1, max_items=3, default=[1, 2]).default == [
        1,
        2,
    ]
    assert _p(name="ts", type="datetime", default="2026-09-01T10:00:00").default == (
        "2026-09-01T10:00:00"
    )
    assert _p(
        name="ts", type="datetime", default="2026-09-01T10:00:00+09:00"
    ).default == "2026-09-01T10:00:00+09:00"


def test_enum_strict_type_and_membership() -> None:
    param = _p(name="status", type="enum", allowed_values=["OPEN", "CLOSED"])
    assert (
        validate_parameter_values([param], {"status": "OPEN"}, []).needs_clarification
        is False
    )
    assert ISSUE_ENUM_NOT_ALLOWED in _codes(
        validate_parameter_values([param], {"status": "OTHER"}, [])
    )
    int_enum = _p(name="code", type="enum", allowed_values=[1, 2])
    assert ISSUE_ENUM_NOT_ALLOWED in _codes(
        validate_parameter_values([int_enum], {"code": "1"}, [])
    )
    assert ISSUE_ENUM_NOT_ALLOWED in _codes(
        validate_parameter_values([int_enum], {"code": True}, [])
    )


def test_lists_and_bounds() -> None:
    s_list = _p(name="tags", type="string_list", min_items=1, max_items=2)
    assert (
        validate_parameter_values([s_list], {"tags": ["a"]}, []).needs_clarification
        is False
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([s_list], {"tags": [1]}, [])
    )
    assert ISSUE_MIN_ITEMS_VIOLATION in _codes(
        validate_parameter_values([s_list], {"tags": []}, [])
    )
    assert ISSUE_MAX_ITEMS_VIOLATION in _codes(
        validate_parameter_values([s_list], {"tags": ["a", "b", "c"]}, [])
    )

    i_list = _p(name="ids", type="integer_list", min_items=1, max_items=2)
    assert (
        validate_parameter_values([i_list], {"ids": [1, 2]}, []).needs_clarification
        is False
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([i_list], {"ids": [True]}, [])
    )
    assert ISSUE_TYPE_MISMATCH in _codes(
        validate_parameter_values([i_list], {"ids": ["1"]}, [])
    )


def test_required_default_optional_unresolved() -> None:
    required = _p(name="req", type="string", required=True)
    with_default = _p(name="defv", type="integer", required=True, default=7)
    optional = _p(name="opt", type="string", required=False)

    missing = validate_parameter_values([required, with_default, optional], {}, [])
    assert ISSUE_MISSING_REQUIRED in _codes(missing)
    assert missing.resolved_parameters == {"defv": 7}
    assert "opt" not in missing.resolved_parameters

    unresolved = validate_parameter_values(
        [required], {}, unresolved_names=["req"]
    )
    assert ISSUE_UNRESOLVED in _codes(unresolved)
