"""Opt-in, development-only Oracle Mock Connection Profile actions.

Do not generalize to DEMIS/replica connectivity. No arbitrary target, SQL or
credential may be supplied by a caller. The read-only probe never mutates the
persistent enabled flag, even when the configured profile is disabled.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.adapters.connection_profile.errors import ConnectionProfileError, ConnectionProfileErrorCode
from app.adapters.demis.credential_factory import create_credential_resolver
from app.adapters.demis.errors import DemisAdapterError, DemisProbeState
from app.adapters.demis.factory import create_readonly_demis_adapter
from app.core.config import Settings
from app.repositories.connection_profile import ConnectionProfileRepository
from app.schemas.connection_profile import (
    ConnectionProfileCreateRequest,
    ConnectionProfileTestConnectionResponse,
    ConnectionProfileView,
)
from app.services.connection_profile import (
    create_connection_profile,
    get_connection_profile,
    enable_connection_profile,
)

MOCK_SOURCE = "oracle_demis_mock"
MOCK_ENVIRONMENT = "development"
MOCK_HOST = "demis-oracle-test"
MOCK_PORT = 1521
MOCK_SERVICE = "FREEPDB1"
MOCK_DBMS = "oracle"
MOCK_USERNAME = "DEMIS_RO"
MOCK_CREDENTIAL_REF = "env:DEMIS_SECRET_ORACLE_PASSWORD"


class OracleMockActionError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def oracle_mock_actions_available(settings: Settings) -> bool:
    return (
        settings.app_env in {"development", "test"}
        and settings.dqa_auth_provider == "dev_headers"
        and settings.dqa_dev_oracle_mock_actions_enabled
    )


def require_mock_actions(settings: Settings) -> None:
    if not oracle_mock_actions_available(settings):
        raise OracleMockActionError("ORACLE_MOCK_ACTIONS_DISABLED")


def _check_mock_target(profile: object) -> None:
    # Every connection-relevant property is pinned, not only source/environment.
    fields = {
        "source_name": MOCK_SOURCE,
        "environment": MOCK_ENVIRONMENT,
        "dbms_type": MOCK_DBMS,
        "host": MOCK_HOST,
        "port": MOCK_PORT,
        "database_name": MOCK_SERVICE,
        "username": MOCK_USERNAME,
        "credential_secret_ref": MOCK_CREDENTIAL_REF,
    }
    if any(getattr(profile, key, None) != expected for key, expected in fields.items()):
        raise OracleMockActionError("ORACLE_MOCK_TARGET_MISMATCH")


def create_or_get_oracle_mock_profile(
    session: Session, settings: Settings, *, actor: str
) -> ConnectionProfileView:
    require_mock_actions(settings)
    repo = ConnectionProfileRepository(session)
    existing = repo.get_by_source_and_environment(MOCK_SOURCE, MOCK_ENVIRONMENT)
    if existing is not None:
        _check_mock_target(existing)
        return get_connection_profile(session, existing.id)
    return create_connection_profile(
        session,
        ConnectionProfileCreateRequest(
            name="DEMIS Oracle Mock - Development",
            source_name=MOCK_SOURCE,
            environment=MOCK_ENVIRONMENT,
            dbms_type=MOCK_DBMS,
            host=MOCK_HOST,
            port=MOCK_PORT,
            database_name=MOCK_SERVICE,
            username=MOCK_USERNAME,
            credential_secret_ref=MOCK_CREDENTIAL_REF,
        ),
        actor=actor,
    )


def register_explicit_oracle_mock_target(
    session: Session, settings: Settings, request: ConnectionProfileCreateRequest, *,
    actor: str,
) -> ConnectionProfileView:
    """No implicit existing-profile selection or client-controlled Mock target."""
    require_mock_actions(settings)
    if request.credential_secret_ref is not None:
        raise OracleMockActionError("ORACLE_MOCK_TARGET_MISMATCH")
    # Check every target field, independently of UI; inject only server-side ref.
    safe_request = request.model_copy(update={
        "credential_secret_ref": MOCK_CREDENTIAL_REF,
    })
    _check_mock_target(safe_request)
    return create_connection_profile(session, safe_request, actor=actor)


def _locked_mock_profile(session: Session, profile_id: int):
    profile = ConnectionProfileRepository(session).get_by_id_for_update(profile_id)
    if profile is None:
        raise ConnectionProfileError(
            ConnectionProfileErrorCode.NOT_FOUND,
            "connection profile not found",
        )
    _check_mock_target(profile)
    return profile


def _probe_mock_profile(profile: object) -> ConnectionProfileTestConnectionResponse:
    # The existing factory intentionally rejects disabled profiles. Create an
    # ephemeral enabled=True snapshot *only for this explicit mock probe*.
    # No persistent enable and no write-capable Oracle grants are involved.
    from app.services.connection_profile import _profile_snapshot

    snapshot = _profile_snapshot(profile).model_copy(update={"enabled": True})
    try:
        adapter = create_readonly_demis_adapter(
            snapshot, credential_resolver=create_credential_resolver()
        )
        result = adapter.probe_readonly()
    except DemisAdapterError as exc:
        probe = exc.probe or DemisProbeState(
            live_connection_tested=False, reachable=None, read_only=None
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
    return ConnectionProfileTestConnectionResponse(
        profile_id=profile.id,
        source_name=profile.source_name,
        environment=profile.environment,
        status="SUCCEEDED",
        live_connection_tested=result.live_connection_tested,
        reachable=result.reachable,
        read_only=result.read_only,
        failure_category=None,
    )


def test_oracle_mock_profile(
    session: Session, profile_id: int, settings: Settings
) -> ConnectionProfileTestConnectionResponse:
    require_mock_actions(settings)
    profile = _locked_mock_profile(session, profile_id)
    return _probe_mock_profile(profile)


def enable_oracle_mock_profile(
    session: Session, profile_id: int, settings: Settings, *, actor: str
) -> ConnectionProfileView:
    require_mock_actions(settings)
    profile = _locked_mock_profile(session, profile_id)
    if not profile.enabled:
        # Repeat probe server-side. Client-reported success can never authorize
        # enable, and changed/failed Oracle connectivity must fail closed.
        result = _probe_mock_profile(profile)
        if (
            result.status != "SUCCEEDED"
            or result.live_connection_tested is not True
            or result.reachable is not True
            or result.read_only is not True
        ):
            raise OracleMockActionError("ORACLE_MOCK_READONLY_PROBE_REQUIRED")
        enable_connection_profile(session, profile_id, actor=actor)
    return get_connection_profile(session, profile_id)
