"""Connection Profile application service (no live DEMIS connectivity)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.connection_profile.errors import (
    ConnectionProfileError,
    ConnectionProfileErrorCode,
)
from app.models.connection_profile import ConnectionProfile
from app.repositories.connection_profile import ConnectionProfileRepository
from app.adapters.demis.credential_factory import create_credential_resolver
from app.adapters.demis.errors import DemisAdapterError, DemisProbeState
from app.adapters.demis.factory import create_readonly_demis_adapter
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.schemas.connection_profile import (
    ConnectionProfileCreateRequest,
    ConnectionProfileDiagnosticsIssue,
    ConnectionProfileDiagnosticsResponse,
    ConnectionProfileListResponse,
    ConnectionProfileTestConnectionResponse,
    ConnectionProfileUpdateRequest,
    ConnectionProfileView,
)

# Reject values that look like inline secrets / DSNs in reference fields.
# Checked in the service so typed errors never echo the rejected input.
_FORBIDDEN_SECRET_MARKERS = (
    "password=",
    "pwd=",
    "passwd=",
)


def create_connection_profile(
    session: Session,
    request: ConnectionProfileCreateRequest,
    *,
    actor: str | None = None,
) -> ConnectionProfileView:
    _assert_credential_ref_is_reference(request.credential_secret_ref)
    repo = ConnectionProfileRepository(session)
    existing = repo.get_by_source_and_environment(
        request.source_name, request.environment
    )
    if existing is not None:
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.DUPLICATE_SOURCE_ENVIRONMENT,
            "a connection profile already exists for this source and environment",
        )

    now = datetime.now(timezone.utc)
    profile = ConnectionProfile(
        name=request.name,
        source_name=request.source_name,
        environment=request.environment,
        enabled=False,
        dbms_type=request.dbms_type,
        host=request.host,
        port=request.port,
        database_name=request.database_name,
        username=request.username,
        credential_secret_ref=request.credential_secret_ref,
        created_by=actor,
        updated_by=actor,
        created_at=now,
        updated_at=now,
    )
    try:
        repo.add(profile)
    except IntegrityError as exc:
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.DUPLICATE_SOURCE_ENVIRONMENT,
            "a connection profile already exists for this source and environment",
        ) from exc
    return _to_view(profile)


def list_connection_profiles(
    session: Session,
    *,
    source_name: str | None = None,
    environment: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> ConnectionProfileListResponse:
    repo = ConnectionProfileRepository(session)
    items = repo.list_profiles(
        source_name=source_name,
        environment=environment,
        limit=limit,
        offset=offset,
    )
    total = repo.count_profiles(source_name=source_name, environment=environment)
    return ConnectionProfileListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=[_to_view(item) for item in items],
    )


def get_connection_profile(session: Session, profile_id: int) -> ConnectionProfileView:
    profile = _require_profile(session, profile_id)
    return _to_view(profile)


def update_connection_profile(
    session: Session,
    profile_id: int,
    request: ConnectionProfileUpdateRequest,
    *,
    actor: str | None = None,
) -> ConnectionProfileView:
    repo = ConnectionProfileRepository(session)
    profile = repo.get_by_id_for_update(profile_id)
    if profile is None:
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.NOT_FOUND,
            "connection profile not found",
        )

    fields = request.model_fields_set
    if "credential_secret_ref" in fields:
        _assert_credential_ref_is_reference(request.credential_secret_ref)
    if "name" in fields and request.name is not None:
        profile.name = request.name
    if "dbms_type" in fields:
        profile.dbms_type = request.dbms_type
    if "host" in fields:
        profile.host = request.host
    if "port" in fields:
        profile.port = request.port
    if "database_name" in fields:
        profile.database_name = request.database_name
    if "username" in fields:
        profile.username = request.username
    if "credential_secret_ref" in fields:
        profile.credential_secret_ref = request.credential_secret_ref

    profile.updated_by = actor
    profile.updated_at = datetime.now(timezone.utc)
    session.flush()
    return _to_view(profile)


def enable_connection_profile(
    session: Session,
    profile_id: int,
    *,
    actor: str | None = None,
) -> ConnectionProfileView:
    return _set_enabled(session, profile_id, enabled=True, actor=actor)


def disable_connection_profile(
    session: Session,
    profile_id: int,
    *,
    actor: str | None = None,
) -> ConnectionProfileView:
    return _set_enabled(session, profile_id, enabled=False, actor=actor)


def test_connection_profile_live_connection(
    session: Session, profile_id: int
) -> ConnectionProfileTestConnectionResponse:
    """Explicit administrator live probe — resolves credentials and opens DEMIS once."""
    profile = _require_profile(session, profile_id)
    snapshot = _profile_snapshot(profile)

    try:
        adapter = create_readonly_demis_adapter(
            snapshot,
            credential_resolver=create_credential_resolver(),
        )
    except DemisAdapterError as exc:
        return _test_connection_failed_response(profile, exc)
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.INTERNAL_ERROR,
            "connection profile live test failed",
        ) from exc

    try:
        probe = adapter.probe_readonly()
    except DemisAdapterError as exc:
        return _test_connection_failed_response(profile, exc)
    except Exception as exc:  # pragma: no cover - defensive boundary
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.INTERNAL_ERROR,
            "connection profile live test failed",
        ) from exc

    return ConnectionProfileTestConnectionResponse(
        profile_id=profile.id,
        source_name=profile.source_name,
        environment=profile.environment,
        status="SUCCEEDED",
        live_connection_tested=probe.live_connection_tested,
        reachable=probe.reachable,
        read_only=probe.read_only,
        failure_category=None,
    )


def get_connection_profile_diagnostics(
    session: Session, profile_id: int
) -> ConnectionProfileDiagnosticsResponse:
    """Return configuration-level sanitized diagnostics.

    Does not open a DEMIS connection and does not resolve credential secrets.
    """
    profile = _require_profile(session, profile_id)
    issues: list[ConnectionProfileDiagnosticsIssue] = []

    credential_configured = bool(profile.credential_secret_ref)
    if not credential_configured:
        issues.append(
            ConnectionProfileDiagnosticsIssue(
                code="CREDENTIAL_REFERENCE_MISSING",
                message="credential secret reference is not configured",
            )
        )

    target_configured = bool(profile.host) and profile.port is not None
    if not target_configured:
        issues.append(
            ConnectionProfileDiagnosticsIssue(
                code="TARGET_METADATA_INCOMPLETE",
                message="non-secret target host/port metadata is incomplete",
            )
        )

    if not credential_configured or not target_configured:
        status = "INCOMPLETE"
    elif profile.enabled:
        status = "CONFIGURED_ENABLED"
    else:
        status = "CONFIGURED_DISABLED"

    return ConnectionProfileDiagnosticsResponse(
        profile_id=profile.id,
        source_name=profile.source_name,
        environment=profile.environment,
        enabled=profile.enabled,
        credential_reference_configured=credential_configured,
        target_metadata_configured=target_configured,
        status=status,
        issues=issues,
        live_connection_tested=False,
    )


def _set_enabled(
    session: Session,
    profile_id: int,
    *,
    enabled: bool,
    actor: str | None,
) -> ConnectionProfileView:
    repo = ConnectionProfileRepository(session)
    profile = repo.get_by_id_for_update(profile_id)
    if profile is None:
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.NOT_FOUND,
            "connection profile not found",
        )
    profile.enabled = enabled
    profile.updated_by = actor
    profile.updated_at = datetime.now(timezone.utc)
    session.flush()
    return _to_view(profile)


def _assert_credential_ref_is_reference(value: str | None) -> None:
    if value is None:
        return
    lowered = value.casefold()
    if any(marker in lowered for marker in _FORBIDDEN_SECRET_MARKERS):
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.INVALID_REQUEST,
            "credential_secret_ref must be a reference, not a secret value",
        )
    if " " in value and "=" in value:
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.INVALID_REQUEST,
            "credential_secret_ref must be a reference, not a secret value",
        )


def _require_profile(session: Session, profile_id: int) -> ConnectionProfile:
    profile = ConnectionProfileRepository(session).get_by_id(profile_id)
    if profile is None:
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.NOT_FOUND,
            "connection profile not found",
        )
    return profile


def _profile_snapshot(profile: ConnectionProfile) -> ConnectionProfileSnapshot:
    return ConnectionProfileSnapshot.model_validate(
        {
            "profile_id": profile.id,
            "name": profile.name,
            "source_name": profile.source_name,
            "environment": profile.environment,
            "enabled": profile.enabled,
            "dbms_type": profile.dbms_type,
            "host": profile.host,
            "port": profile.port,
            "database_name": profile.database_name,
            "username": profile.username,
            "credential_secret_ref": profile.credential_secret_ref,
        }
    )


def _test_connection_failed_response(
    profile: ConnectionProfile,
    exc: DemisAdapterError,
) -> ConnectionProfileTestConnectionResponse:
    probe = exc.probe or DemisProbeState(
        live_connection_tested=False,
        reachable=None,
        read_only=None,
    )
    return ConnectionProfileTestConnectionResponse(
        profile_id=profile.id,
        source_name=profile.source_name,
        environment=profile.environment,
        status="FAILED",
        live_connection_tested=probe.live_connection_tested,
        reachable=probe.reachable,
        read_only=probe.read_only,
        failure_category=exc.failure_category,
    )


def _to_view(profile: ConnectionProfile) -> ConnectionProfileView:
    return ConnectionProfileView(
        id=profile.id,
        name=profile.name,
        source_name=profile.source_name,
        environment=profile.environment,
        enabled=profile.enabled,
        dbms_type=profile.dbms_type,
        host=profile.host,
        port=profile.port,
        database_name=profile.database_name,
        username=profile.username,
        credential_secret_ref=profile.credential_secret_ref,
        created_by=profile.created_by,
        updated_by=profile.updated_by,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )
