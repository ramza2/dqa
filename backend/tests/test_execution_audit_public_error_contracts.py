"""Fail-closed public error contracts for audit and query execution APIs."""

from __future__ import annotations

import json

import pytest

from app.adapters.audit.errors import AuditError, AuditErrorCode
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.execution.errors import (
    ExecutionError,
    ExecutionErrorCode,
    ExecutionPreviewError,
    ExecutionPreviewErrorCode,
)
from app.api.routes.audit_events import _audit_http_error
from app.api.routes.query_executions import (
    _adapter_http_error,
    _eligibility_http_error,
    _execution_http_error,
)

RAW_INTERNAL_DETAIL = (
    "super-secret-db-password postgresql+psycopg:// "
    "Traceback (most recent call last) "
    "SELECT secret_patient_id FROM dual row_secret_phi_value"
)


def _assert_sanitized(detail: object) -> None:
    rendered = json.dumps(detail, default=str)
    for fragment in (
        "super-secret-db-password",
        "postgresql+psycopg://",
        "Traceback (most recent call last)",
        "SELECT secret_patient_id FROM dual",
        "row_secret_phi_value",
    ):
        assert fragment not in rendered


@pytest.mark.parametrize(
    ("code", "status_code", "public_code"),
    [
        (AuditErrorCode.NOT_FOUND, 404, AuditErrorCode.NOT_FOUND),
        (AuditErrorCode.INVALID_REQUEST, 422, AuditErrorCode.INVALID_REQUEST),
        ("UNREVIEWED_AUDIT_ERROR", 500, AuditErrorCode.INTERNAL_ERROR),
    ],
)
def test_audit_public_error_contract(
    code: str,
    status_code: int,
    public_code: str,
) -> None:
    public = _audit_http_error(AuditError(code, RAW_INTERNAL_DETAIL))

    assert public.status_code == status_code
    assert public.detail["code"] == public_code
    _assert_sanitized(public.detail)


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        (ExecutionPreviewErrorCode.TEMPLATE_NOT_FOUND, 404),
        (ExecutionPreviewErrorCode.ACTIVE_CATALOG_NOT_FOUND, 404),
        (ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND, 404),
        (ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE, 409),
        (ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION, 409),
        (ExecutionPreviewErrorCode.CATALOG_MISMATCH, 409),
        (ExecutionPreviewErrorCode.CONNECTION_PROFILE_DISABLED, 409),
        (ExecutionPreviewErrorCode.CONNECTION_PROFILE_INCOMPLETE, 409),
        (ExecutionPreviewErrorCode.SQL_UNSAFE, 422),
        (ExecutionPreviewErrorCode.PARAMETER_SCHEMA_INVALID, 422),
        (ExecutionPreviewErrorCode.PARAMETER_UNDECLARED, 422),
        (ExecutionPreviewErrorCode.PARAMETER_INVALID, 422),
    ],
)
def test_execution_preview_public_error_contract_known_codes(
    code: str,
    status_code: int,
) -> None:
    public = _eligibility_http_error(ExecutionPreviewError(code, RAW_INTERNAL_DETAIL))

    assert public.status_code == status_code
    assert public.detail["code"] == code
    _assert_sanitized(public.detail)


def test_execution_preview_unknown_error_fails_closed() -> None:
    public = _eligibility_http_error(
        ExecutionPreviewError("UNREVIEWED_EXECUTION_PREVIEW_ERROR", RAW_INTERNAL_DETAIL)
    )

    assert public.status_code == 500
    assert public.detail["code"] == ExecutionPreviewErrorCode.INTERNAL_ERROR
    _assert_sanitized(public.detail)


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        (ExecutionErrorCode.AUDIT_UNAVAILABLE, 503),
        (ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE, 503),
    ],
)
def test_query_execution_public_error_contract_known_codes(
    code: str,
    status_code: int,
) -> None:
    public = _execution_http_error(ExecutionError(code, RAW_INTERNAL_DETAIL))

    assert public.status_code == status_code
    assert public.detail["code"] == code
    _assert_sanitized(public.detail)


def test_query_execution_unknown_error_fails_closed() -> None:
    public = _execution_http_error(
        ExecutionError("UNREVIEWED_QUERY_EXECUTION_ERROR", RAW_INTERNAL_DETAIL)
    )

    assert public.status_code == 500
    assert public.detail["code"] == ExecutionErrorCode.INTERNAL_ERROR
    _assert_sanitized(public.detail)


@pytest.mark.parametrize(
    ("code", "status_code", "public_code"),
    [
        (DemisAdapterErrorCode.TIMEOUT, 504, DemisAdapterErrorCode.TIMEOUT),
        (
            DemisAdapterErrorCode.UNSUPPORTED_DBMS,
            503,
            DemisAdapterErrorCode.UNSUPPORTED_DBMS,
        ),
        (
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
            503,
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
        ),
        (
            DemisAdapterErrorCode.CONNECTION_FAILED,
            503,
            DemisAdapterErrorCode.CONNECTION_FAILED,
        ),
        (
            DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED,
            503,
            DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED,
        ),
        (
            DemisAdapterErrorCode.PROFILE_DISABLED,
            503,
            DemisAdapterErrorCode.PROFILE_DISABLED,
        ),
        (
            DemisAdapterErrorCode.EXECUTION_FAILED,
            502,
            DemisAdapterErrorCode.EXECUTION_FAILED,
        ),
        (
            DemisAdapterErrorCode.RESULT_LIMIT_ERROR,
            502,
            DemisAdapterErrorCode.RESULT_LIMIT_ERROR,
        ),
        (
            DemisAdapterErrorCode.INVALID_REQUEST,
            422,
            DemisAdapterErrorCode.INVALID_REQUEST,
        ),
        (
            "UNREVIEWED_DEMIS_ADAPTER_ERROR",
            502,
            DemisAdapterErrorCode.EXECUTION_FAILED,
        ),
    ],
)
def test_demis_adapter_shared_public_error_contract(
    code: str,
    status_code: int,
    public_code: str,
) -> None:
    public = _adapter_http_error(DemisAdapterError(code, RAW_INTERNAL_DETAIL))

    assert public.status_code == status_code
    assert public.detail["code"] == public_code
    _assert_sanitized(public.detail)
