"""Fail-closed public error contracts for non-LLM domain APIs."""

from __future__ import annotations

import json

import pytest

from app.adapters.catalog.activation_errors import (
    CatalogActivationError,
    CatalogActivationErrorCode,
)
from app.adapters.catalog.errors import CatalogPackageErrorCode, CatalogPackageValidationError
from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.adapters.catalog.query_template_errors import (
    QueryTemplateError,
    QueryTemplateErrorCode,
)
from app.adapters.connection_profile.errors import (
    ConnectionProfileError,
    ConnectionProfileErrorCode,
)
from app.api.routes.catalog_active import activation_http_error
from app.api.routes.catalog_packages import _validation_http_error
from app.api.routes.catalog_query import _query_http_error as _catalog_query_http_error
from app.api.routes.connection_profiles import _profile_http_error
from app.api.routes.query_templates import (
    _catalog_query_http_error as _template_catalog_http_error,
)
from app.api.routes.query_templates import _template_http_error

RAW_INTERNAL_DETAIL = (
    "super-secret-db-password postgresql+psycopg:// "
    "Traceback (most recent call last) "
    "SELECT secret_patient_id FROM dual row_secret_phi_value"
)


def _assert_sanitized(detail: object) -> None:
    rendered = json.dumps(detail, default=str)
    assert RAW_INTERNAL_DETAIL not in rendered
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
        (
            ConnectionProfileErrorCode.NOT_FOUND,
            404,
            ConnectionProfileErrorCode.NOT_FOUND,
        ),
        (
            ConnectionProfileErrorCode.DUPLICATE_SOURCE_ENVIRONMENT,
            409,
            ConnectionProfileErrorCode.DUPLICATE_SOURCE_ENVIRONMENT,
        ),
        (
            ConnectionProfileErrorCode.INVALID_REQUEST,
            422,
            ConnectionProfileErrorCode.INVALID_REQUEST,
        ),
        (
            "UNREVIEWED_CONNECTION_PROFILE_ERROR",
            500,
            ConnectionProfileErrorCode.INTERNAL_ERROR,
        ),
    ],
)
def test_connection_profile_public_error_contract(
    code: str,
    status_code: int,
    public_code: str,
) -> None:
    public = _profile_http_error(ConnectionProfileError(code, RAW_INTERNAL_DETAIL))

    assert public.status_code == status_code
    assert public.detail["code"] == public_code
    _assert_sanitized(public.detail)


@pytest.mark.parametrize(
    ("code", "status_code", "public_code"),
    [
        (
            CatalogActivationErrorCode.IMPORT_NOT_FOUND,
            404,
            CatalogActivationErrorCode.IMPORT_NOT_FOUND,
        ),
        (
            CatalogActivationErrorCode.ACTIVE_REVISION_NOT_FOUND,
            404,
            CatalogActivationErrorCode.ACTIVE_REVISION_NOT_FOUND,
        ),
        (
            CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE,
            409,
            CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE,
        ),
        (
            "UNREVIEWED_CATALOG_ACTIVATION_ERROR",
            500,
            CatalogActivationErrorCode.INTERNAL_ERROR,
        ),
    ],
)
def test_catalog_activation_public_error_contract(
    code: str,
    status_code: int,
    public_code: str,
) -> None:
    public = activation_http_error(CatalogActivationError(code, RAW_INTERNAL_DETAIL))

    assert public.status_code == status_code
    assert public.detail["code"] == public_code
    _assert_sanitized(public.detail)


@pytest.mark.parametrize(
    ("code", "status_code", "public_code"),
    [
        (
            CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND,
            404,
            CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND,
        ),
        (
            CatalogQueryErrorCode.TABLE_NOT_FOUND,
            404,
            CatalogQueryErrorCode.TABLE_NOT_FOUND,
        ),
        (
            "UNREVIEWED_CATALOG_QUERY_ERROR",
            500,
            CatalogQueryErrorCode.INTERNAL_ERROR,
        ),
    ],
)
def test_catalog_query_public_error_contract(
    code: str,
    status_code: int,
    public_code: str,
) -> None:
    public = _catalog_query_http_error(CatalogQueryError(code, RAW_INTERNAL_DETAIL))

    assert public.status_code == status_code
    assert public.detail["code"] == public_code
    _assert_sanitized(public.detail)


@pytest.mark.parametrize(
    ("code", "status_code"),
    [
        (QueryTemplateErrorCode.TEMPLATE_NOT_FOUND, 404),
        (QueryTemplateErrorCode.VERSION_NOT_FOUND, 404),
        (QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND, 404),
        (QueryTemplateErrorCode.DUPLICATE_STABLE_KEY, 409),
        (QueryTemplateErrorCode.NOT_DRAFT, 409),
        (QueryTemplateErrorCode.INVALID_TRANSITION, 409),
        (QueryTemplateErrorCode.STABLE_METADATA_FROZEN, 409),
        (QueryTemplateErrorCode.INCOMPATIBLE_CATALOG, 409),
        (QueryTemplateErrorCode.INVALID_PARAMETER_SCHEMA, 422),
        (QueryTemplateErrorCode.INVALID_TARGET_SCHEMA, 422),
        (QueryTemplateErrorCode.INVALID_REQUEST, 422),
    ],
)
def test_query_template_public_error_contract_known_codes(
    code: str,
    status_code: int,
) -> None:
    public = _template_http_error(QueryTemplateError(code, RAW_INTERNAL_DETAIL))

    assert public.status_code == status_code
    assert public.detail["code"] == code
    _assert_sanitized(public.detail)


def test_query_template_public_error_contract_unknown_fails_closed() -> None:
    public = _template_http_error(
        QueryTemplateError("UNREVIEWED_QUERY_TEMPLATE_ERROR", RAW_INTERNAL_DETAIL)
    )

    assert public.status_code == 500
    assert public.detail["code"] == QueryTemplateErrorCode.INTERNAL_ERROR
    _assert_sanitized(public.detail)


def test_query_template_catalog_error_alias_is_reviewed() -> None:
    public = _template_catalog_http_error(
        CatalogQueryError(
            CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND,
            RAW_INTERNAL_DETAIL,
        )
    )

    assert public.status_code == 404
    assert public.detail["code"] == QueryTemplateErrorCode.ACTIVE_CATALOG_NOT_FOUND
    _assert_sanitized(public.detail)


def test_query_template_catalog_unknown_fails_closed() -> None:
    public = _template_catalog_http_error(
        CatalogQueryError("UNREVIEWED_TEMPLATE_CATALOG_ERROR", RAW_INTERNAL_DETAIL)
    )

    assert public.status_code == 500
    assert public.detail["code"] == QueryTemplateErrorCode.INTERNAL_ERROR
    _assert_sanitized(public.detail)


_CATALOG_PACKAGE_KNOWN_CODES = (
    CatalogPackageErrorCode.INVALID_ZIP,
    CatalogPackageErrorCode.ARCHIVE_TOO_LARGE,
    CatalogPackageErrorCode.TOO_MANY_ENTRIES,
    CatalogPackageErrorCode.UNCOMPRESSED_TOO_LARGE,
    CatalogPackageErrorCode.COMPRESSION_RATIO,
    CatalogPackageErrorCode.UNSAFE_PATH,
    CatalogPackageErrorCode.INVALID_ROOT,
    CatalogPackageErrorCode.DUPLICATE_ENTRY,
    CatalogPackageErrorCode.NON_REGULAR_ENTRY,
    CatalogPackageErrorCode.UNEXPECTED_FILE,
    CatalogPackageErrorCode.MISSING_MANIFEST,
    CatalogPackageErrorCode.MALFORMED_MANIFEST,
    CatalogPackageErrorCode.INVALID_PACKAGE_FORMAT,
    CatalogPackageErrorCode.UNSUPPORTED_VERSION,
    CatalogPackageErrorCode.INVALID_READINESS,
    CatalogPackageErrorCode.MISSING_SOURCE,
    CatalogPackageErrorCode.MISSING_FINGERPRINT,
    CatalogPackageErrorCode.INVALID_MANIFEST_FILES,
    CatalogPackageErrorCode.MISSING_REQUIRED_FILE,
    CatalogPackageErrorCode.CHECKSUM_MISMATCH,
    CatalogPackageErrorCode.BYTES_MISMATCH,
    CatalogPackageErrorCode.MALFORMED_JSON,
    CatalogPackageErrorCode.SOURCE_MISMATCH,
    CatalogPackageErrorCode.FINGERPRINT_MISMATCH,
    CatalogPackageErrorCode.COUNTS_MISMATCH,
    CatalogPackageErrorCode.EMPTY_UPLOAD,
    CatalogPackageErrorCode.FORBIDDEN_SECRET_FIELD,
)

_CATALOG_PACKAGE_TOO_LARGE_CODES = {
    CatalogPackageErrorCode.ARCHIVE_TOO_LARGE,
    CatalogPackageErrorCode.UNCOMPRESSED_TOO_LARGE,
    CatalogPackageErrorCode.TOO_MANY_ENTRIES,
}


@pytest.mark.parametrize("code", _CATALOG_PACKAGE_KNOWN_CODES)
def test_catalog_package_public_error_contract_known_codes(code: str) -> None:
    public = _validation_http_error(
        CatalogPackageValidationError(
            code,
            RAW_INTERNAL_DETAIL,
            path="demis_catalog_package/tables.json",
        )
    )

    assert public.status_code == (
        413 if code in _CATALOG_PACKAGE_TOO_LARGE_CODES else 400
    )
    assert public.detail["code"] == code
    assert public.detail["path"] == "demis_catalog_package/tables.json"
    _assert_sanitized(public.detail)


def test_catalog_package_public_error_contract_unknown_fails_closed() -> None:
    public = _validation_http_error(
        CatalogPackageValidationError(
            "UNREVIEWED_CATALOG_PACKAGE_ERROR",
            RAW_INTERNAL_DETAIL,
            path="attacker-controlled-path",
        )
    )

    assert public.status_code == 500
    assert public.detail["code"] == CatalogPackageErrorCode.INTERNAL_ERROR
    assert public.detail["path"] is None
    _assert_sanitized(public.detail)
