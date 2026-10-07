"""Production Readiness Report — read-only preflight for real DEMIS use.

Inspects DQA application metadata/config only. Never resolves DEMIS credentials,
opens DEMIS sockets, mutates schema/data, or persists probe results.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.db.migration_head import inspect_migration_head
from app.adapters.demis.factory import (
    is_concrete_demis_adapter_available,
    required_adapter_config_present,
)
from app.core.config import Settings, get_settings
from app.repositories.catalog_active import CatalogActiveRepository
from app.repositories.catalog_import import CatalogImportRepository
from app.repositories.connection_profile import ConnectionProfileRepository
from app.repositories.query_template import QueryTemplateRepository
from app.schemas.production_readiness import (
    ProductionReadinessReport,
    ReadinessCheckResult,
)
from app.services.sql_safety import validate_sql_safety

_CHECK_ORDER = (
    "MIGRATIONS_AT_HEAD",
    "AUTH_PROVIDER",
    "ACTIVE_CATALOG",
    "QUERY_TEMPLATE",
    "CONNECTION_PROFILE",
    "DEMIS_ADAPTER",
    "LIVE_CONNECTIVITY",
    "EXTERNAL_READONLY_PRIVILEGE",
)


def build_production_readiness_report(
    session: Session,
    *,
    source_name: str,
    environment: str,
    settings: Settings | None = None,
) -> ProductionReadinessReport:
    """Build a sanitized readiness report for ``source_name`` / ``environment``."""
    cfg = settings or get_settings()
    source = source_name.strip()
    env = environment.strip()
    if not source or not env:
        raise ValueError("source_name and environment are required")

    checks: list[ReadinessCheckResult] = [
        _check_migrations_at_head(),
        _check_auth_provider(cfg),
        _check_active_catalog(session, source),
        _check_query_templates(session, source),
        _check_connection_profile(session, source, env),
        _check_demis_adapter(session, source, env),
        _check_live_connectivity(),
        _check_external_readonly_privilege(),
    ]
    # Preserve declared order even if a helper returns unexpected codes.
    by_code = {item.code: item for item in checks}
    ordered = [by_code[code] for code in _CHECK_ORDER if code in by_code]

    overall = "READY" if all(item.status == "PASS" for item in ordered) else "NOT_READY"
    return ProductionReadinessReport(
        source_name=source,
        environment=env,
        overall_status=overall,
        checks=ordered,
    )


def _check_migrations_at_head() -> ReadinessCheckResult:
    status = inspect_migration_head()
    if status.ok:
        return ReadinessCheckResult(
            code="MIGRATIONS_AT_HEAD",
            status="PASS",
            message="DQA database is at the current Alembic head",
        )
    return ReadinessCheckResult(
        code="MIGRATIONS_AT_HEAD",
        status="BLOCKED",
        message="DQA database is not at the current Alembic head",
    )


def _check_auth_provider(settings: Settings) -> ReadinessCheckResult:
    # No approved production IdP is implemented. Production is always BLOCKED
    # for AUTH_PROVIDER until a reviewed IdP lands in a later PR.
    if settings.app_env == "production":
        return ReadinessCheckResult(
            code="AUTH_PROVIDER",
            status="BLOCKED",
            message="no approved production identity provider is configured",
        )
    if settings.dqa_auth_provider == "dev_headers" and settings.app_env in {
        "development",
        "test",
    }:
        return ReadinessCheckResult(
            code="AUTH_PROVIDER",
            status="ACTION_REQUIRED",
            message=(
                "dev_headers is active for non-production use only; "
                "approved production identity provider is required"
            ),
        )
    return ReadinessCheckResult(
        code="AUTH_PROVIDER",
        status="BLOCKED",
        message="authentication provider is not configured for production readiness",
    )


def _check_active_catalog(session: Session, source_name: str) -> ReadinessCheckResult:
    pointer = CatalogActiveRepository(session).get_active_by_source_name(source_name)
    if pointer is None:
        return ReadinessCheckResult(
            code="ACTIVE_CATALOG",
            status="BLOCKED",
            message="no active Catalog Package revision for source",
        )
    revision = CatalogImportRepository(session).get_by_id(
        pointer.catalog_import_revision_id
    )
    if revision is None or revision.package_readiness != "READY":
        return ReadinessCheckResult(
            code="ACTIVE_CATALOG",
            status="BLOCKED",
            message="active Catalog Package revision is not READY",
        )
    return ReadinessCheckResult(
        code="ACTIVE_CATALOG",
        status="PASS",
        message="active Catalog Package revision is READY",
    )


def _check_query_templates(session: Session, source_name: str) -> ReadinessCheckResult:
    pointer = CatalogActiveRepository(session).get_active_by_source_name(source_name)
    if pointer is None:
        return ReadinessCheckResult(
            code="QUERY_TEMPLATE",
            status="BLOCKED",
            message="no eligible approved Query Template for active Catalog",
        )
    revision = CatalogImportRepository(session).get_by_id(
        pointer.catalog_import_revision_id
    )
    if revision is None:
        return ReadinessCheckResult(
            code="QUERY_TEMPLATE",
            status="BLOCKED",
            message="no eligible approved Query Template for active Catalog",
        )

    rows = QueryTemplateRepository(session).list_approved_enabled_current_versions(
        source_name=source_name
    )
    eligible = 0
    for _template, version in rows:
        if version.catalog_revision_id != revision.id:
            continue
        if version.catalog_fingerprint_constraint != revision.schema_fingerprint:
            continue
        report = validate_sql_safety(version.sql_text, version.parameter_schema)
        if report.safe:
            eligible += 1

    if eligible < 1:
        return ReadinessCheckResult(
            code="QUERY_TEMPLATE",
            status="BLOCKED",
            message="no eligible approved Query Template for active Catalog",
        )
    return ReadinessCheckResult(
        code="QUERY_TEMPLATE",
        status="PASS",
        message=f"eligible approved Query Template count={eligible}",
    )


def _check_connection_profile(
    session: Session, source_name: str, environment: str
) -> ReadinessCheckResult:
    profile = ConnectionProfileRepository(session).get_by_source_and_environment(
        source_name, environment
    )
    if profile is None:
        return ReadinessCheckResult(
            code="CONNECTION_PROFILE",
            status="BLOCKED",
            message="connection profile not found for source and environment",
        )
    if not profile.enabled:
        return ReadinessCheckResult(
            code="CONNECTION_PROFILE",
            status="BLOCKED",
            message="connection profile is disabled",
        )
    if not required_adapter_config_present(
        dbms_type=profile.dbms_type,
        host=profile.host,
        port=profile.port,
        database_name=profile.database_name,
        username=profile.username,
        credential_secret_ref=profile.credential_secret_ref,
    ):
        return ReadinessCheckResult(
            code="CONNECTION_PROFILE",
            status="BLOCKED",
            message="connection profile adapter configuration is incomplete",
        )
    return ReadinessCheckResult(
        code="CONNECTION_PROFILE",
        status="PASS",
        message="enabled connection profile has required adapter configuration",
    )


def _check_demis_adapter(
    session: Session, source_name: str, environment: str
) -> ReadinessCheckResult:
    profile = ConnectionProfileRepository(session).get_by_source_and_environment(
        source_name, environment
    )
    if profile is None or not profile.enabled:
        return ReadinessCheckResult(
            code="DEMIS_ADAPTER",
            status="BLOCKED",
            message="no enabled connection profile available for DEMIS adapter check",
        )
    if not is_concrete_demis_adapter_available(profile.dbms_type):
        return ReadinessCheckResult(
            code="DEMIS_ADAPTER",
            status="BLOCKED",
            message="no concrete DEMIS read-only adapter is registered for profile DBMS",
        )
    return ReadinessCheckResult(
        code="DEMIS_ADAPTER",
        status="PASS",
        message="concrete DEMIS read-only adapter is registered for profile DBMS",
    )


def _check_live_connectivity() -> ReadinessCheckResult:
    # Never auto-probe. Phase 25-A results are not persisted.
    return ReadinessCheckResult(
        code="LIVE_CONNECTIVITY",
        status="ACTION_REQUIRED",
        message=(
            "explicit administrator live connection probe required "
            "(POST /api/v1/connection-profiles/{profile_id}/test-connection)"
        ),
    )


def _check_external_readonly_privilege() -> ReadinessCheckResult:
    return ReadinessCheckResult(
        code="EXTERNAL_READONLY_PRIVILEGE",
        status="ACTION_REQUIRED",
        message=(
            "external DBA verification required for DEMIS account read-only "
            "privileges and risky function/package EXECUTE restrictions"
        ),
    )
