"""S-05-C2: structural-only comparison of independent target metadata.

No DB I/O, DNS, credential resolution, engine creation or operator-config update.
A structural match can NEVER authorize a connection or activate an Inspector.
"""
from __future__ import annotations

from app.core.config import Settings
from app.schemas.connection_profile import ConnectionProfileView
from app.schemas.inspector_target_review import InspectorTargetReviewResponse
from app.services.schema_inspection import SchemaInspectionError, _target_from_settings


def review_inspector_target_configuration(
    profile: ConnectionProfileView,
    settings: Settings,
) -> InspectorTargetReviewResponse:
    """Compare existing record and server-only Inspector operator configuration.

    The effective Inspector target is still sourced ONLY from server settings.
    Connection Profile data is never passed into schema_inspection; a match is
    merely an advisory comparison and not DBA/DEC-01/DEC-10 verification.
    """
    state = "CONFIGURED_UNVERIFIED"
    target = None
    try:
        target = _target_from_settings(settings)
    except SchemaInspectionError as exc:
        state = {
            "INSPECTOR_DISABLED": "DISABLED",
            "INSPECTOR_ENV_NOT_ALLOWED": "ENV_BLOCKED",
        }.get(exc.code, "INVALID")

    differences: list[str] = []
    if target is not None:
        expected = {
            "environment": (profile.environment, settings.app_env),
            "source_name": (profile.source_name, target.source_name),
            "dbms_type": (profile.dbms_type.casefold() if profile.dbms_type else None, "oracle"),
            "host": (profile.host, target.host),
            "port": (profile.port, target.port),
            # A Connection Profile's generic database_name is *not* guaranteed
            # to mean Oracle service_name. Even exact text match is unverified.
            "database_name_vs_service_name": (profile.database_name, target.service_name),
            "username": (profile.username, target.username),
        }
        differences = [
            field for field, (actual, desired) in expected.items()
            if actual != desired
        ]
    return InspectorTargetReviewResponse(
        profile_id=profile.id,
        inspector_configuration_state=state,
        comparison_state=(
            "NOT_COMPARABLE" if target is None
            else "TARGET_METADATA_MISMATCH" if differences
            else "STRUCTURAL_MATCH_UNVERIFIED"
        ),
        mismatch_fields=differences,
        profile_enabled=profile.enabled,
    )
