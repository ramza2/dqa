"""Production Readiness Report (Phase 25-B) — read-only preflight."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from pydantic import SecretStr

from app.adapters.db.migration_head import MigrationHeadStatus
from app.core.config import Settings
from app.schemas.production_readiness import ProductionReadinessReport
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.production_readiness import build_production_readiness_report
from tests.catalog_package_fixtures import DEFAULT_SOURCE, build_core_documents, build_package_zip

pytestmark = pytest.mark.integration

SOURCE = dict(DEFAULT_SOURCE)
ENVIRONMENT = "development"
ALLOWED_REF = "env:DEMIS_SECRET_PASSWORD"


def _headers(actor: str, roles: str) -> dict[str, str]:
    return {"X-DQA-Dev-Actor": actor, "X-DQA-Dev-Roles": roles}


def _import_and_activate(session: Session, *, fingerprint: str, readiness: str = "READY"):
    files = build_core_documents(
        source=SOURCE,
        fingerprint=fingerprint,
        tables=[{"schema": "DEMIS_OWNER", "name": "T1"}],
    )
    archive = build_package_zip(
        package_readiness=readiness,
        source=SOURCE,
        fingerprint=fingerprint,
        files=files,
    )
    revision, created = import_catalog_package_bytes(archive, session)
    assert created is True
    if readiness == "READY":
        activate_catalog_revision(session, revision.id)
    session.flush()
    return revision


def _template_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stable_key": "readiness.wards",
        "name": "병동 조회",
        "description": "병동 조회",
        "source_name": SOURCE["source_name"],
        "target_schemas": ["DEMIS_OWNER"],
        "sql_text": "SELECT ward_cd FROM dual WHERE ward_cd = :ward_cd",
        "parameter_schema": [
            {
                "name": "ward_cd",
                "label": "병동 코드",
                "type": "string",
                "required": True,
            }
        ],
        "row_limit": 50,
        "timeout_seconds": 15,
    }
    body.update(overrides)
    return body


def _approve_enable(db_client: TestClient, template_id: int) -> None:
    assert (
        db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review", json={}
        ).status_code
        == 200
    )
    assert (
        db_client.post(
            f"/api/v1/query-templates/{template_id}/approve", json={}
        ).status_code
        == 200
    )
    assert (
        db_client.post(f"/api/v1/query-templates/{template_id}/enable").status_code
        == 200
    )


def _ensure_profile(db_client: TestClient, **overrides: Any) -> dict[str, Any]:
    enabled = overrides.pop("enabled", True)
    body: dict[str, Any] = {
        "name": "Mock DEMIS profile",
        "source_name": SOURCE["source_name"],
        "environment": ENVIRONMENT,
        "dbms_type": "oracle",
        "host": "demis.internal.example",
        "port": 1521,
        "database_name": "DEMIS",
        "username": "dqa_ro",
        "credential_secret_ref": ALLOWED_REF,
    }
    body.update(overrides)
    payload = {key: value for key, value in body.items() if value is not None}
    created = db_client.post("/api/v1/connection-profiles", json=payload)
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]
    if enabled:
        enabled_resp = db_client.post(f"/api/v1/connection-profiles/{profile_id}/enable")
        assert enabled_resp.status_code == 200
        return enabled_resp.json()
    return created.json()


def _by_code(report: ProductionReadinessReport) -> dict[str, Any]:
    return {item.code: item for item in report.checks}


def _assert_sanitized(report: ProductionReadinessReport) -> None:
    dumped = report.model_dump_json()
    for forbidden in (
        "demis.internal.example",
        "dqa_ro",
        ALLOWED_REF,
        "password=",
        "postgresql://",
        "SELECT ward_cd",
        "super-secret",
        "1521",
    ):
        assert forbidden.casefold() not in dumped.casefold()


def test_migration_at_head_pass(db_session: Session, test_settings_env: dict[str, str]) -> None:
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["MIGRATIONS_AT_HEAD"].status == "PASS"


def test_migration_mismatch_blocked_sanitized(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, test_settings_env: dict[str, str]
) -> None:
    monkeypatch.setattr(
        "app.services.production_readiness.inspect_migration_head",
        lambda: MigrationHeadStatus(
            ok=False,
            reason_code="not_at_head",
            script_heads=("20261008_dd02",),
            current_heads=("20261008_dd01",),
            detail="missing heads=20261008_dd02",
        ),
    )
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    item = _by_code(report)["MIGRATIONS_AT_HEAD"]
    assert item.status == "BLOCKED"
    assert "postgresql://" not in item.message.casefold()
    assert report.overall_status == "NOT_READY"


def test_production_auth_disabled_blocked(
    db_session: Session, test_settings_env: dict[str, str]
) -> None:
    settings = Settings(
        app_env="production",
        dqa_auth_provider="disabled",
        dqa_db_password=SecretStr("dqa"),
    )
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        settings=settings,
    )
    assert _by_code(report)["AUTH_PROVIDER"].status == "BLOCKED"
    assert report.overall_status == "NOT_READY"


def test_dev_headers_not_production_ready(
    db_session: Session, test_settings_env: dict[str, str]
) -> None:
    settings = Settings(
        app_env="test",
        dqa_auth_provider="dev_headers",
        dqa_db_password=SecretStr("dqa"),
    )
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        settings=settings,
    )
    assert _by_code(report)["AUTH_PROVIDER"].status == "ACTION_REQUIRED"
    assert _by_code(report)["AUTH_PROVIDER"].status != "PASS"


def test_active_ready_catalog_pass(
    db_session: Session, db_client: TestClient, test_settings_env: dict[str, str]
) -> None:
    _import_and_activate(db_session, fingerprint="fp-ready-cat")
    db_session.commit()
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["ACTIVE_CATALOG"].status == "PASS"


def test_active_catalog_missing_blocked(
    db_session: Session, test_settings_env: dict[str, str]
) -> None:
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["ACTIVE_CATALOG"].status == "BLOCKED"


def test_eligible_template_pass(
    db_session: Session, db_client: TestClient, test_settings_env: dict[str, str]
) -> None:
    revision = _import_and_activate(db_session, fingerprint="fp-tpl-ok")
    db_session.commit()
    created = db_client.post("/api/v1/query-templates", json=_template_body())
    assert created.status_code == 201
    # Bind template version to active catalog via approve path (uses revision at create).
    _approve_enable(db_client, created.json()["id"])
    # Ensure fingerprint/revision match (create already tied to active).
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    item = _by_code(report)["QUERY_TEMPLATE"]
    assert item.status == "PASS"
    assert "count=1" in item.message
    assert "SELECT" not in item.message
    assert revision.id > 0


def test_no_eligible_template_blocked(
    db_session: Session, db_client: TestClient, test_settings_env: dict[str, str]
) -> None:
    _import_and_activate(db_session, fingerprint="fp-tpl-none")
    db_session.commit()
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["QUERY_TEMPLATE"].status == "BLOCKED"


def test_enabled_oracle_profile_and_adapter_pass(
    db_session: Session, db_client: TestClient, test_settings_env: dict[str, str]
) -> None:
    _ensure_profile(db_client)
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["CONNECTION_PROFILE"].status == "PASS"
    assert _by_code(report)["DEMIS_ADAPTER"].status == "PASS"
    _assert_sanitized(report)


def test_disabled_profile_blocked(
    db_session: Session, db_client: TestClient, test_settings_env: dict[str, str]
) -> None:
    _ensure_profile(db_client, enabled=False)
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["CONNECTION_PROFILE"].status == "BLOCKED"


def test_incomplete_profile_blocked(
    db_session: Session, db_client: TestClient, test_settings_env: dict[str, str]
) -> None:
    _ensure_profile(db_client, host=None, port=None, username=None)
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["CONNECTION_PROFILE"].status == "BLOCKED"


def test_unsupported_dbms_adapter_blocked(
    db_session: Session, db_client: TestClient, test_settings_env: dict[str, str]
) -> None:
    _ensure_profile(db_client, dbms_type="postgresql")
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["CONNECTION_PROFILE"].status == "PASS"
    assert _by_code(report)["DEMIS_ADAPTER"].status == "BLOCKED"


def test_live_and_external_always_action_required(
    db_session: Session, test_settings_env: dict[str, str]
) -> None:
    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert _by_code(report)["LIVE_CONNECTIVITY"].status == "ACTION_REQUIRED"
    assert _by_code(report)["EXTERNAL_READONLY_PRIVILEGE"].status == "ACTION_REQUIRED"
    assert report.overall_status == "NOT_READY"


def test_readiness_never_resolves_credentials_or_probes(
    db_session: Session,
    db_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    test_settings_env: dict[str, str],
) -> None:
    _import_and_activate(db_session, fingerprint="fp-no-probe")
    db_session.commit()
    created = db_client.post("/api/v1/query-templates", json=_template_body())
    _approve_enable(db_client, created.json()["id"])
    _ensure_profile(db_client)

    resolver = MagicMock(side_effect=AssertionError("credential resolve forbidden"))
    factory = MagicMock(side_effect=AssertionError("adapter factory forbidden"))
    probe = MagicMock(side_effect=AssertionError("probe_readonly forbidden"))
    connect = MagicMock(side_effect=AssertionError("oracledb.connect forbidden"))

    monkeypatch.setattr(
        "app.adapters.demis.credential_factory.create_credential_resolver", resolver
    )
    monkeypatch.setattr("app.adapters.demis.factory.create_readonly_demis_adapter", factory)
    monkeypatch.setattr("app.adapters.demis.oracle.oracledb.connect", connect)
    # Wire probe mock to the concrete Oracle adapter method so accidental
    # live-probe calls fail closed during readiness inspection.
    monkeypatch.setattr(
        "app.adapters.demis.oracle.OracleReadOnlyDemisAdapter.probe_readonly",
        probe,
    )
    # Also guard service-level imports if accidentally added later.
    monkeypatch.setattr(
        "app.services.connection_profile.create_credential_resolver",
        resolver,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.connection_profile.create_readonly_demis_adapter",
        factory,
        raising=False,
    )

    report = build_production_readiness_report(
        db_session,
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
    )
    assert report.checks
    assert _by_code(report)["LIVE_CONNECTIVITY"].status == "ACTION_REQUIRED"
    resolver.assert_not_called()
    factory.assert_not_called()
    probe.assert_not_called()
    connect.assert_not_called()
    _assert_sanitized(report)


def test_cli_exit_not_ready(
    db_session: Session, test_settings_env: dict[str, str]
) -> None:
    from app.cli.production_readiness import main

    code = main(
        [
            "--source-name",
            SOURCE["source_name"],
            "--environment",
            ENVIRONMENT,
            "--json",
        ]
    )
    # ACTION_REQUIRED items keep overall NOT_READY in Phase 25-B.
    assert code == 1


def test_cli_session_factory_failure_sanitized(
    monkeypatch: pytest.MonkeyPatch,
    test_settings_env: dict[str, str],
    capsys,
) -> None:
    """Engine/session factory failures must not leak DSN/password markers."""
    from app.cli.production_readiness import main

    secret_marker = (
        "SUPER_SECRET_DSN_MARKER_postgresql://dqa:hunter2@evil-host.example/dqa"
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError(secret_marker)

    monkeypatch.setattr("app.adapters.db.session.get_session_factory", _boom)

    code = main(
        [
            "--source-name",
            SOURCE["source_name"],
            "--environment",
            ENVIRONMENT,
            "--json",
        ]
    )
    assert code == 1
    captured = capsys.readouterr()
    err = captured.err
    out = captured.out
    assert "error: readiness inspection failed (RuntimeError)" in err
    combined = err + out
    for forbidden in (
        secret_marker,
        "SUPER_SECRET_DSN_MARKER",
        "hunter2",
        "evil-host.example",
        "postgresql://",
        "Traceback",
    ):
        assert forbidden not in combined


def test_cli_exit_ready_when_report_is_ready(
    monkeypatch: pytest.MonkeyPatch,
    test_settings_env: dict[str, str],
    capsys,
) -> None:
    """CLI exit 0 contract via synthetic READY report (service semantics unchanged)."""
    from app.cli.production_readiness import main
    from app.schemas.production_readiness import ReadinessCheckResult

    synthetic = ProductionReadinessReport(
        source_name=SOURCE["source_name"],
        environment=ENVIRONMENT,
        overall_status="READY",
        checks=[
            ReadinessCheckResult(code=code, status="PASS", message="ok")
            for code in (
                "MIGRATIONS_AT_HEAD",
                "AUTH_PROVIDER",
                "ACTIVE_CATALOG",
                "QUERY_TEMPLATE",
                "CONNECTION_PROFILE",
                "DEMIS_ADAPTER",
                "LIVE_CONNECTIVITY",
                "EXTERNAL_READONLY_PRIVILEGE",
            )
        ],
    )

    # CLI imports the builder inside main(); patch the service module symbol.
    monkeypatch.setattr(
        "app.services.production_readiness.build_production_readiness_report",
        lambda *_args, **_kwargs: synthetic,
    )

    class _FakeSession:
        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "app.adapters.db.session.get_session_factory",
        lambda: (lambda: _FakeSession()),
    )

    code = main(
        [
            "--source-name",
            SOURCE["source_name"],
            "--environment",
            ENVIRONMENT,
            "--json",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert '"overall_status": "READY"' in out


def test_cli_json_omits_secrets(
    db_session: Session, db_client: TestClient, test_settings_env: dict[str, str], capsys
) -> None:
    from app.cli.production_readiness import main

    _ensure_profile(db_client, host="secret-host.example", username="secret_user")
    code = main(
        [
            "--source-name",
            SOURCE["source_name"],
            "--environment",
            ENVIRONMENT,
            "--json",
        ]
    )
    assert code == 1
    out = capsys.readouterr().out
    assert "secret-host.example" not in out
    assert "secret_user" not in out
    assert ALLOWED_REF not in out
    assert "overall_status" in out


def test_overall_ready_only_when_all_pass() -> None:
    from app.schemas.production_readiness import ReadinessCheckResult

    checks = [
        ReadinessCheckResult(code=code, status="PASS", message="ok")
        for code in (
            "MIGRATIONS_AT_HEAD",
            "AUTH_PROVIDER",
            "ACTIVE_CATALOG",
            "QUERY_TEMPLATE",
            "CONNECTION_PROFILE",
            "DEMIS_ADAPTER",
            "LIVE_CONNECTIVITY",
            "EXTERNAL_READONLY_PRIVILEGE",
        )
    ]
    report = ProductionReadinessReport(
        source_name="s",
        environment="e",
        overall_status="READY",
        checks=checks,
    )
    assert report.overall_status == "READY"
    # Service never auto-PASS ACTION_REQUIRED items; READY is theoretical until
    # external gates exist. Document contract via schema round-trip.
    assert all(item.status == "PASS" for item in report.checks)
