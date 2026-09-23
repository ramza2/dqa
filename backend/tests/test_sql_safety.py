"""Focused SQL Safety Validator tests (parser/AST allowlist; no DB execution)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.catalog.sql_safety_codes import SqlSafetyIssueCode
from app.schemas.query_template import QueryTemplateParameter
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.sql_safety import (
    SqlSafetyValidationError,
    require_sql_safe,
    validate_sql_safety,
)
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)

SOURCE_A = dict(DEFAULT_SOURCE)


def _p(*names: str) -> list[QueryTemplateParameter]:
    return [QueryTemplateParameter(name=name, type="string") for name in names]


def _assert_safe(sql: str, params: list[QueryTemplateParameter] | None = None) -> None:
    report = validate_sql_safety(sql, params or [])
    assert report.safe is True, report.model_dump()
    assert report.issues == []


def _assert_unsafe(
    sql: str,
    *,
    params: list[QueryTemplateParameter] | None = None,
    codes: set[str] | None = None,
) -> None:
    """Reject SQL and require every expected issue code to be present (subset)."""
    report = validate_sql_safety(sql, params or [])
    assert report.safe is False, report.model_dump()
    if codes is not None:
        found = {issue.code for issue in report.issues}
        assert codes <= found, (codes, found, report.model_dump())


def _assert_unsafe_any_of(
    sql: str,
    *,
    params: list[QueryTemplateParameter] | None = None,
    codes: set[str],
) -> None:
    """Reject SQL when parser yield is dialect-dependent (any expected code)."""
    report = validate_sql_safety(sql, params or [])
    assert report.safe is False, report.model_dump()
    found = {issue.code for issue in report.issues}
    assert codes & found, (codes, found, report.model_dump())


@pytest.mark.parametrize(
    "sql,params",
    [
        ("SELECT 1 FROM dual", []),
        ("SELECT ENC_ID FROM DEMIS_OWNER.TB_ENC_HIST WHERE ENC_ID = :enc_id", _p("enc_id")),
        (
            "SELECT * FROM T WHERE A = :id OR B = :id",
            _p("id"),
        ),
        (
            """
            WITH enc AS (
              SELECT ENC_ID
              FROM DEMIS_OWNER.TB_ENC_HIST
              WHERE PAT_ID = :patient_id
            )
            SELECT * FROM enc
            """,
            _p("patient_id"),
        ),
        (
            "SELECT a.ENC_ID FROM T a JOIN U b ON a.ID = b.ID WHERE a.X = :x",
            _p("x"),
        ),
        (
            "SELECT * FROM T WHERE ENC_ID IN (SELECT ENC_ID FROM U WHERE Y = :y)",
            _p("y"),
        ),
        (
            "SELECT COUNT(*) AS CNT FROM T WHERE STATUS = :status GROUP BY STATUS",
            _p("status"),
        ),
        (
            "SELECT ENC_ID FROM T WHERE STATUS = :status ORDER BY ENC_ID",
            _p("status"),
        ),
        (
            "SELECT CASE WHEN X = :flag THEN 1 ELSE 0 END AS V FROM dual",
            [QueryTemplateParameter(name="flag", type="integer")],
        ),
        ("SELECT 1 FROM dual;", []),
        ("SELECT '; DELETE FROM X' AS TXT FROM DUAL", []),
        ("SELECT ';' AS TXT FROM dual", []),
        ("SELECT 1 FROM dual -- ;", []),
        ("SELECT 1 FROM DUAL -- DELETE FROM T", []),
        ("SELECT /* DROP TABLE X */ 1 FROM DUAL", []),
        (
            "SELECT TRUNC(SYSDATE) AS D FROM dual WHERE CREATED_AT >= :since_dt",
            _p("since_dt"),
        ),
        (
            "SELECT * FROM T WHERE Name = :Name",
            [QueryTemplateParameter(name="name", type="string")],
        ),
    ],
)
def test_allowed_sql(sql: str, params: list[QueryTemplateParameter]) -> None:
    _assert_safe(sql, params)
    assert require_sql_safe(sql, params).safe is True


@pytest.mark.parametrize(
    "sql,codes",
    [
        ("", {SqlSafetyIssueCode.PARSE_ERROR}),
        ("   ", {SqlSafetyIssueCode.PARSE_ERROR}),
        ("SELECT FROM", {SqlSafetyIssueCode.PARSE_ERROR}),
        (
            "SELECT * FROM T; SELECT 1 FROM dual",
            {SqlSafetyIssueCode.MULTIPLE_STATEMENTS},
        ),
        (
            "SELECT * FROM T; DELETE FROM T2",
            {SqlSafetyIssueCode.MULTIPLE_STATEMENTS},
        ),
        ("; SELECT 1 FROM dual", {SqlSafetyIssueCode.MULTIPLE_STATEMENTS}),
        ("SELECT 1 FROM dual;;", {SqlSafetyIssueCode.MULTIPLE_STATEMENTS}),
        ("SELECT 1 FROM dual; ;", {SqlSafetyIssueCode.MULTIPLE_STATEMENTS}),
        ("; ;", {SqlSafetyIssueCode.MULTIPLE_STATEMENTS}),
        ("SELECT 1 FROM dual;;;", {SqlSafetyIssueCode.MULTIPLE_STATEMENTS}),
        ("INSERT INTO T (A) VALUES (1)", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("UPDATE T SET A = 1", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("DELETE FROM T", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("MERGE INTO T USING S ON (1=1) WHEN MATCHED THEN UPDATE SET A=1", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("CREATE TABLE T (A INT)", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("ALTER TABLE T ADD A INT", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("DROP TABLE T", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("TRUNCATE TABLE T", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("GRANT SELECT ON T TO U", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("COMMIT", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("CALL foo()", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("EXECUTE IMMEDIATE 'x'", {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        (
            "WITH x AS (SELECT 1 AS a FROM dual) UPDATE t SET a = 1",
            {SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED},
        ),
        (
            "WITH x AS (DELETE FROM T RETURNING *) SELECT * FROM x",
            {SqlSafetyIssueCode.FORBIDDEN_CONSTRUCT},
        ),
        ("SELECT * FROM T FOR UPDATE", {SqlSafetyIssueCode.FOR_UPDATE_FORBIDDEN}),
        ("SELECT a INTO b FROM T", {SqlSafetyIssueCode.SELECT_INTO_FORBIDDEN}),
        ("SELECT * FROM T WHERE id = ?", {SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN}),
        ("SELECT * FROM T WHERE id = $1", {SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN}),
        ("SELECT * FROM T WHERE id = {{name}}", {SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN}),
        ("SELECT * FROM T WHERE id = ${name}", {SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN}),
        (
            "SELECT * FROM :table_name",
            {SqlSafetyIssueCode.DYNAMIC_IDENTIFIER_FORBIDDEN},
        ),
        (
            "SELECT :column_name FROM DEMIS_OWNER.T",
            {SqlSafetyIssueCode.DYNAMIC_IDENTIFIER_FORBIDDEN},
        ),
    ],
)
def test_rejected_sql(sql: str, codes: set[str]) -> None:
    _assert_unsafe(sql, codes=codes)


@pytest.mark.parametrize(
    "sql,codes",
    [
        # Dialect-dependent: may surface as parse failure or as forbidden statement.
        ("REVOKE SELECT ON T FROM U", {SqlSafetyIssueCode.PARSE_ERROR, SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("BEGIN NULL; END;", {SqlSafetyIssueCode.PARSE_ERROR, SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("EXEC foo", {SqlSafetyIssueCode.PARSE_ERROR, SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED}),
        ("SELECT * FROM T WHERE id = :1", {SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN, SqlSafetyIssueCode.PARSE_ERROR}),
        ("SELECT * FROM T WHERE id = %s", {SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN, SqlSafetyIssueCode.PARSE_ERROR}),
        ("SELECT * FROM T WHERE id = %(name)s", {SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN, SqlSafetyIssueCode.PARSE_ERROR}),
    ],
)
def test_rejected_sql_parser_alternatives(sql: str, codes: set[str]) -> None:
    _assert_unsafe_any_of(sql, codes=codes)


def test_undeclared_and_unused_parameters() -> None:
    _assert_unsafe(
        "SELECT * FROM T WHERE ENC_ID = :enc_id",
        params=_p("patient_id"),
        codes={
            SqlSafetyIssueCode.UNDECLARED_PARAMETER,
            SqlSafetyIssueCode.UNUSED_DECLARED_PARAMETER,
        },
    )


def test_referenced_parameters_use_declared_canonical_spelling() -> None:
    report = validate_sql_safety(
        "SELECT * FROM T WHERE Name = :Name",
        [QueryTemplateParameter(name="name", type="string")],
    )
    assert report.safe is True
    assert report.referenced_parameters == ["name"]
    assert report.declared_parameters == ["name"]


def test_require_sql_safe_returns_report_when_safe() -> None:
    report = require_sql_safe("SELECT 1 FROM dual", [])
    assert report.safe is True
    assert report.issues == []


def test_require_sql_safe_raises_when_unsafe() -> None:
    with pytest.raises(SqlSafetyValidationError) as exc_info:
        require_sql_safe("DELETE FROM T", [])
    error = exc_info.value
    assert error.report.safe is False
    found = {issue.code for issue in error.report.issues}
    assert SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED in found
    # Fail-closed helper must not embed the full original SQL in the message.
    assert "DELETE FROM T" not in str(error)


def test_issue_order_is_deterministic() -> None:
    report = validate_sql_safety(
        "SELECT * FROM T WHERE A = :a AND B = :b",
        _p("z"),
    )
    codes = [issue.code for issue in report.issues]
    assert codes == sorted(codes)
    messages = [issue.message for issue in report.issues]
    assert messages == sorted(messages)


def test_literal_and_comment_do_not_false_positive() -> None:
    _assert_safe("SELECT '?:$1 {{x}} ${y} %s' AS TXT FROM dual")
    _assert_safe("SELECT 1 FROM dual -- :missing and DELETE FROM T")


def _import_and_activate(session: Session, *, fingerprint: str) -> None:
    files = build_core_documents(
        source=SOURCE_A,
        fingerprint=fingerprint,
        tables=[{"schema": "DEMIS_OWNER", "name": "T1"}],
    )
    archive = build_package_zip(
        package_readiness="READY",
        source=SOURCE_A,
        fingerprint=fingerprint,
        files=files,
    )
    revision, created = import_catalog_package_bytes(archive, session)
    assert created is True
    activate_catalog_revision(session, revision.id)
    session.flush()


def test_sql_safety_api_for_stored_template(
    db_session: Session, db_client: TestClient
) -> None:
    pytest.importorskip("sqlglot")
    _import_and_activate(db_session, fingerprint="fp-sql-safe-api")
    db_session.commit()

    created = db_client.post(
        "/api/v1/query-templates",
        json={
            "stable_key": "sql_safe_api",
            "name": "Safety API",
            "source_name": SOURCE_A["source_name"],
            "target_schemas": ["DEMIS_OWNER"],
            "sql_text": "SELECT 1 FROM dual WHERE id = :enc_id",
            "parameter_schema": [{"name": "enc_id", "type": "integer", "required": True}],
            "row_limit": 10,
            "timeout_seconds": 5,
        },
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]

    ok = db_client.get(f"/api/v1/query-templates/{template_id}/sql-safety")
    assert ok.status_code == 200
    body = ok.json()
    assert body["safe"] is True
    assert body["template_id"] == template_id
    assert body["referenced_parameters"] == ["enc_id"]
    assert body["declared_parameters"] == ["enc_id"]
    assert body["issues"] == []

    # Approve does not require SQL safety; unsafe SQL still returns 200 + safe=false.
    bad = db_client.post(
        "/api/v1/query-templates",
        json={
            "stable_key": "sql_unsafe_api",
            "name": "Unsafe API",
            "source_name": SOURCE_A["source_name"],
            "target_schemas": ["DEMIS_OWNER"],
            "sql_text": "DELETE FROM T",
            "parameter_schema": [],
            "row_limit": 10,
            "timeout_seconds": 5,
        },
    )
    assert bad.status_code == 201
    unsafe = db_client.get(f"/api/v1/query-templates/{bad.json()['id']}/sql-safety")
    assert unsafe.status_code == 200
    assert unsafe.json()["safe"] is False
    assert any(
        issue["code"] == SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED
        for issue in unsafe.json()["issues"]
    )


def test_sql_safety_api_unknown_template_404(db_client: TestClient) -> None:
    response = db_client.get("/api/v1/query-templates/999999/sql-safety")
    assert response.status_code == 404
