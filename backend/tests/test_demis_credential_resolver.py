"""EnvironmentCredentialResolver production boundary tests."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from app.adapters.demis import (
    DemisAdapterError,
    DemisAdapterErrorCode,
    EnvironmentCredentialResolver,
    create_credential_resolver,
    create_readonly_demis_adapter,
)
from app.adapters.demis.env_credentials import validate_demis_credential_env_prefix
from app.adapters.demis.fake import FakeCredentialResolver
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.core.config import Settings
from app.services.connection_profile import get_connection_profile_diagnostics


ALLOWED_REF = "env:DEMIS_SECRET_PASSWORD"
SECRET_VALUE = "unit-test-demis-secret"


def _eligible_snapshot(**overrides: object) -> ConnectionProfileSnapshot:
    body: dict[str, object] = {
        "profile_id": 1,
        "name": "Mock DEMIS profile",
        "source_name": "oracle_demis_mock",
        "environment": "dev",
        "enabled": True,
        "dbms_type": "oracle",
        "host": "demis.internal.example",
        "port": 1521,
        "database_name": "DEMIS",
        "username": "dqa_ro",
        "credential_secret_ref": ALLOWED_REF,
    }
    body.update(overrides)
    return ConnectionProfileSnapshot.model_validate(body)


def _resolver(
    mapping: dict[str, str] | None = None,
    *,
    prefix: str = "DEMIS_SECRET_",
) -> EnvironmentCredentialResolver:
    return EnvironmentCredentialResolver(
        env_prefix=prefix,
        environ=mapping if mapping is not None else { "DEMIS_SECRET_PASSWORD": SECRET_VALUE },
    )


def test_valid_allowed_env_reference_resolves() -> None:
    material = _resolver().resolve(ALLOWED_REF)
    assert material.get_secret() == SECRET_VALUE
    assert SECRET_VALUE not in repr(material)
    assert SECRET_VALUE not in str(material)
    assert ALLOWED_REF not in repr(material)
    assert "DEMIS_SECRET_PASSWORD" not in repr(material)


def test_oracle_suffix_allowed() -> None:
    resolver = _resolver({"DEMIS_SECRET_ORACLE_PASSWORD": "ora-secret"})
    material = resolver.resolve("env:DEMIS_SECRET_ORACLE_PASSWORD")
    assert material.get_secret() == "ora-secret"
    assert "ora-secret" not in repr(material)


def test_missing_variable_fails_closed() -> None:
    resolver = _resolver({})
    with pytest.raises(DemisAdapterError) as exc:
        resolver.resolve(ALLOWED_REF)
    assert exc.value.code == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE
    text = str(exc.value) + repr(exc.value)
    assert SECRET_VALUE not in text
    assert ALLOWED_REF not in text
    assert "DEMIS_SECRET_PASSWORD" not in text


def test_empty_variable_fails_closed() -> None:
    resolver = _resolver({"DEMIS_SECRET_PASSWORD": ""})
    with pytest.raises(DemisAdapterError) as exc:
        resolver.resolve(ALLOWED_REF)
    assert exc.value.code == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE


def test_invalid_env_name_rejected() -> None:
    for ref in (
        "env:demis_secret_password",
        "env:DEMIS-SECRET-PASSWORD",
        "env:1DEMIS_SECRET_PASSWORD",
        "env:DEMIS_SECRET_PASSWORD;id",
        "env:",
        "env: ",
    ):
        with pytest.raises(DemisAdapterError) as exc:
            _resolver().resolve(ref)
        assert exc.value.code == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE
        assert ref not in str(exc.value)


def test_wrong_prefix_rejected() -> None:
    resolver = _resolver(
        {
            "DEMIS_SECRET_PASSWORD": SECRET_VALUE,
            "DQA_DB_PASSWORD": "dqa-db-secret",
            "AWS_SECRET_ACCESS_KEY": "aws-secret",
            "PATH": "/usr/bin",
            "HOME": "/root",
        }
    )
    for ref in (
        "env:DQA_DB_PASSWORD",
        "env:AWS_SECRET_ACCESS_KEY",
        "env:PATH",
        "env:HOME",
        "env:DEMIS_DB_PASSWORD",
    ):
        with pytest.raises(DemisAdapterError) as exc:
            resolver.resolve(ref)
        assert exc.value.code == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE
        text = str(exc.value) + repr(exc.value)
        assert "dqa-db-secret" not in text
        assert "aws-secret" not in text
        assert "/usr/bin" not in text
        assert ref not in text


def test_unsupported_schemes_rejected() -> None:
    resolver = _resolver()
    for ref in (
        "file:/etc/passwd",
        "vault:secret/data/demis",
        "secret-value-as-password",
        SECRET_VALUE,
        "ENV:DEMIS_SECRET_PASSWORD",
        "environ:DEMIS_SECRET_PASSWORD",
        "",
        "   ",
    ):
        with pytest.raises(DemisAdapterError) as exc:
            resolver.resolve(ref)
        assert exc.value.code == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE
        assert SECRET_VALUE not in str(exc.value)


def test_does_not_treat_ref_as_password() -> None:
    # Mapping keys are env var names, not refs; resolving must never return the
    # reference string itself as the secret.
    resolver = _resolver({ALLOWED_REF: "should-never-be-used"})
    with pytest.raises(DemisAdapterError) as exc:
        resolver.resolve(ALLOWED_REF)
    assert exc.value.code == DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE


def test_invalid_configured_prefix_rejected() -> None:
    with pytest.raises(DemisAdapterError) as exc:
        validate_demis_credential_env_prefix("demis_secret_")
    assert exc.value.code == DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED
    assert "demis_secret_" not in str(exc.value)

    with pytest.raises(DemisAdapterError) as exc2:
        EnvironmentCredentialResolver(env_prefix="bad-prefix")
    assert exc2.value.code == DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED


def test_create_credential_resolver_uses_settings_prefix() -> None:
    settings = Settings(
        APP_ENV="test",
        DQA_DEMIS_CREDENTIAL_ENV_PREFIX="DEMIS_SECRET_",
    )
    resolver = create_credential_resolver(settings)
    assert isinstance(resolver, EnvironmentCredentialResolver)
    assert resolver.env_prefix == "DEMIS_SECRET_"
    material = EnvironmentCredentialResolver(
        env_prefix=resolver.env_prefix,
        environ={"DEMIS_SECRET_PASSWORD": SECRET_VALUE},
    ).resolve(ALLOWED_REF)
    assert material.get_secret() == SECRET_VALUE


def test_secret_ref_env_name_absent_from_errors_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    resolver = _resolver({})
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(DemisAdapterError) as exc:
            resolver.resolve(ALLOWED_REF)
        logging.getLogger("test.credentials").info("failed: %r", exc.value)
    joined = "\n".join(record.getMessage() for record in caplog.records)
    assert ALLOWED_REF not in joined
    assert "DEMIS_SECRET_PASSWORD" not in joined
    assert SECRET_VALUE not in joined


def test_unsupported_dbms_does_not_invoke_env_resolver() -> None:
    resolve = MagicMock(side_effect=AssertionError("resolve must not be called"))
    resolver = MagicMock()
    resolver.resolve = resolve
    with pytest.raises(DemisAdapterError) as exc:
        create_readonly_demis_adapter(
            _eligible_snapshot(dbms_type="oracle"),
            credential_resolver=resolver,
        )
    assert exc.value.code == DemisAdapterErrorCode.UNSUPPORTED_DBMS
    resolve.assert_not_called()


def test_fake_kinds_do_not_invoke_env_resolver() -> None:
    resolve = MagicMock(side_effect=AssertionError("resolve must not be called"))
    resolver = MagicMock()
    resolver.resolve = resolve
    for kind in ("fake", "test", "mock", "memory"):
        with pytest.raises(DemisAdapterError) as exc:
            create_readonly_demis_adapter(
                _eligible_snapshot(dbms_type=kind),
                credential_resolver=resolver,
            )
        assert exc.value.code == DemisAdapterErrorCode.UNSUPPORTED_DBMS
    resolve.assert_not_called()


@pytest.mark.integration
def test_connection_profile_diagnostics_do_not_resolve_secret(
    db_session, db_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolve = MagicMock(side_effect=AssertionError("resolve must not be called"))
    monkeypatch.setattr(
        EnvironmentCredentialResolver,
        "resolve",
        resolve,
        raising=False,
    )
    created = db_client.post(
        "/api/v1/connection-profiles",
        json={
            "name": "cred-diag",
            "source_name": "oracle_demis_mock",
            "environment": "cred-diag",
            "dbms_type": "oracle",
            "host": "demis.internal.example",
            "port": 1521,
            "database_name": "DEMIS",
            "username": "dqa_ro",
            "credential_secret_ref": ALLOWED_REF,
        },
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]
    diag = db_client.get(f"/api/v1/connection-profiles/{profile_id}/diagnostics")
    assert diag.status_code == 200
    assert diag.json()["credential_reference_configured"] is True
    assert diag.json()["live_connection_tested"] is False
    assert SECRET_VALUE not in diag.text
    resolve.assert_not_called()
    # Service-level diagnostics path
    service_diag = get_connection_profile_diagnostics(db_session, profile_id)
    assert service_diag.credential_reference_configured is True
    resolve.assert_not_called()


@pytest.mark.integration
def test_execution_preview_does_not_resolve_secret(
    db_session, db_client, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services.catalog_active import activate_catalog_revision
    from app.services.catalog_package_import import import_catalog_package_bytes
    from tests.catalog_package_fixtures import (
        DEFAULT_SOURCE,
        build_core_documents,
        build_package_zip,
    )

    resolve = MagicMock(side_effect=AssertionError("resolve must not be called"))
    monkeypatch.setattr(EnvironmentCredentialResolver, "resolve", resolve)

    source = dict(DEFAULT_SOURCE)
    files = build_core_documents(
        source=source,
        fingerprint="fp-cred-preview",
        tables=[{"schema": "DEMIS_OWNER", "name": "T1"}],
    )
    archive = build_package_zip(
        package_readiness="READY",
        source=source,
        fingerprint="fp-cred-preview",
        files=files,
    )
    revision, created = import_catalog_package_bytes(archive, db_session)
    assert created is True
    activate_catalog_revision(db_session, revision.id)
    db_session.commit()

    template = db_client.post(
        "/api/v1/query-templates",
        json={
            "stable_key": "cred.preview",
            "name": "cred preview",
            "source_name": source["source_name"],
            "target_schemas": ["DEMIS_OWNER"],
            "sql_text": "SELECT 1 FROM dual WHERE ward_cd = :ward_cd",
            "parameter_schema": [
                {
                    "name": "ward_cd",
                    "label": "병동",
                    "type": "string",
                    "required": True,
                }
            ],
            "row_limit": 10,
            "timeout_seconds": 5,
        },
    )
    assert template.status_code == 201, template.text
    tid = template.json()["id"]
    assert db_client.post(
        f"/api/v1/query-templates/{tid}/submit-review", json={}
    ).status_code == 200
    assert db_client.post(
        f"/api/v1/query-templates/{tid}/approve", json={}
    ).status_code == 200
    enabled = db_client.post(f"/api/v1/query-templates/{tid}/enable")
    assert enabled.status_code == 200
    profile = db_client.post(
        "/api/v1/connection-profiles",
        json={
            "name": "cred-preview-profile",
            "source_name": source["source_name"],
            "environment": "cred-preview",
            "dbms_type": "oracle",
            "host": "demis.internal.example",
            "port": 1521,
            "database_name": "DEMIS",
            "username": "dqa_ro",
            "credential_secret_ref": ALLOWED_REF,
        },
    )
    assert profile.status_code == 201
    assert (
        db_client.post(
            f"/api/v1/connection-profiles/{profile.json()['id']}/enable"
        ).status_code
        == 200
    )

    preview = db_client.post(
        "/api/v1/query-executions/preview",
        json={
            "source_name": source["source_name"],
            "environment": "cred-preview",
            "template_id": tid,
            "version_id": enabled.json()["version"]["id"],
            "parameters": {"ward_cd": "A01"},
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["execution_available"] is False
    assert SECRET_VALUE not in preview.text
    assert ALLOWED_REF not in preview.text
    resolve.assert_not_called()


def test_credential_material_redaction_intact() -> None:
    material = FakeCredentialResolver({ALLOWED_REF: SECRET_VALUE}).resolve(ALLOWED_REF)
    assert material.get_secret() == SECRET_VALUE
    assert SECRET_VALUE not in repr(material)
    assert SECRET_VALUE not in str(material)
    assert "<redacted>" in repr(material)
