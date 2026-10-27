"""M2-1B: selected Oracle Mock Profile -> separately configured Inspector guard.

No DB connection here; never infer approval from an enabled Connection Profile.
All actual Oracle metadata reads stay in schema_inspection using its independent
DEMIS_INSPECT_SECRET_* credential domain. Mock identity is strictly pinned.
"""
from __future__ import annotations

from app.adapters.connection_profile.errors import ConnectionProfileError
from app.core.config import Settings
from app.schemas.connection_profile import ConnectionProfileView
from app.services.connection_profile import get_connection_profile
from app.services.oracle_mock_actions import (
    OracleMockActionError, _check_mock_target, require_mock_actions,
)
from app.services.schema_inspection import SchemaInspectionError, _target_from_settings
from sqlalchemy.orm import Session


class MockInspectorBindingError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require_mock_inspector_binding(
    session: Session, profile_id: int, settings: Settings,
) -> ConnectionProfileView:
    """Fail before secret resolution/network/metadata capture on ANY mismatch."""
    try:
        require_mock_actions(settings)
    except OracleMockActionError:
        raise MockInspectorBindingError("MOCK_INSPECTOR_DISABLED") from None

    try:
        profile = get_connection_profile(session, profile_id)
    except ConnectionProfileError:
        raise MockInspectorBindingError("MOCK_PROFILE_NOT_FOUND") from None

    try:
        _check_mock_target(profile)
    except OracleMockActionError:
        raise MockInspectorBindingError("MOCK_PROFILE_MISMATCH") from None

    if not profile.enabled:
        raise MockInspectorBindingError("MOCK_PROFILE_INACTIVE")

    try:
        target = _target_from_settings(settings)
    except SchemaInspectionError as exc:
        raise MockInspectorBindingError(exc.code) from None

    # Match only physical instance identity. The dedicated Inspector account
    # MUST differ from the read-query account (never compare them for equality).
    if (
        profile.source_name != target.source_name
        or profile.host != target.host
        or profile.port != target.port
        or profile.database_name != target.service_name
    ):
        raise MockInspectorBindingError("MOCK_INSPECTOR_TARGET_MISMATCH")

    if (
        profile.username is None
        or profile.username.casefold() == target.username.casefold()
        or profile.credential_secret_ref == target.credential_ref
    ):
        raise MockInspectorBindingError("MOCK_INSPECTOR_ACCOUNT_NOT_SEPARATE")

    # All conditions are runtime DEV gates only, not military/DBA privileges.
    return profile
