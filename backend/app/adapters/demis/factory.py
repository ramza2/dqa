"""Production factory for ReadOnlyDemisAdapter — fail-closed without concrete DBMS."""

from __future__ import annotations

from app.adapters.demis.credentials import CredentialResolver
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.adapters.demis.protocol import ReadOnlyDemisAdapter

# Known DBMS labels that may appear on Connection Profiles. None are implemented
# until DEMIS requirements confirm a concrete driver. Listing them documents that
# recognition is not the same as support.
_KNOWN_UNIMPLEMENTED_DBMS = frozenset(
    {
        "oracle",
        "postgresql",
        "postgres",
        "mysql",
        "mariadb",
        "sqlserver",
        "mssql",
        "unspecified",
    }
)

# Explicitly rejected adapter kinds that must never be selected in production.
_FORBIDDEN_PRODUCTION_KINDS = frozenset({"fake", "test", "mock", "memory"})


def create_readonly_demis_adapter(
    profile: ConnectionProfileSnapshot,
    *,
    credential_resolver: CredentialResolver,
) -> ReadOnlyDemisAdapter:
    """Build a live-capable read-only DEMIS adapter from a validated profile.

    Fail-closed rules for this foundation:
    - disabled profiles are rejected
    - required non-secret target metadata must be present
    - ``credential_secret_ref`` is required and must resolve
    - no concrete DBMS driver is registered yet → ``UNSUPPORTED_DBMS``
    - fake/test adapters are never selectable through this factory
    - never falls back to DQA PostgreSQL / psycopg
    """
    _validate_profile_eligibility(profile)
    _reject_forbidden_adapter_kind(profile.dbms_type)

    # Resolve credentials before DBMS selection so missing secrets fail with the
    # credential category rather than masking as unsupported DBMS.
    try:
        material = credential_resolver.resolve(profile.credential_secret_ref or "")
    except DemisAdapterError:
        raise
    except Exception as exc:  # pragma: no cover - defensive sanitization
        raise DemisAdapterError(
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
            "credential reference could not be resolved",
        ) from exc

    # Touch material only to prove resolution succeeded; never log get_secret().
    if not material.get_secret():
        raise DemisAdapterError(
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
            "credential reference resolved to empty material",
        )

    dbms = (profile.dbms_type or "").strip().casefold()
    if not dbms:
        raise DemisAdapterError(
            DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED,
            "connection profile dbms_type is required for adapter creation",
        )

    # No concrete DEMIS driver is registered. Fail closed — do not use DQA DB.
    raise DemisAdapterError(
        DemisAdapterErrorCode.UNSUPPORTED_DBMS,
        "no concrete DEMIS read-only adapter is registered for the configured DBMS; "
        "blocked until DEMIS DBMS/driver requirements are confirmed",
    )


def _validate_profile_eligibility(profile: ConnectionProfileSnapshot) -> None:
    if not profile.enabled:
        raise DemisAdapterError(
            DemisAdapterErrorCode.PROFILE_DISABLED,
            "connection profile is disabled",
        )

    missing: list[str] = []
    if not profile.dbms_type:
        missing.append("dbms_type")
    if not profile.host:
        missing.append("host")
    if profile.port is None:
        missing.append("port")
    if not profile.database_name:
        missing.append("database_name")
    if not profile.username:
        missing.append("username")
    if missing:
        # Do not echo host/username/database values — only field names.
        raise DemisAdapterError(
            DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED,
            "connection profile target metadata incomplete: " + ", ".join(missing),
        )

    if not profile.credential_secret_ref:
        raise DemisAdapterError(
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
            "credential secret reference is required for adapter creation",
        )


def _reject_forbidden_adapter_kind(dbms_type: str | None) -> None:
    label = (dbms_type or "").strip().casefold()
    if label in _FORBIDDEN_PRODUCTION_KINDS:
        raise DemisAdapterError(
            DemisAdapterErrorCode.UNSUPPORTED_DBMS,
            "test/fake DEMIS adapters cannot be selected through the production factory",
        )
    # Recognized but unimplemented labels still fail closed below; this helper
    # only blocks explicit fake/test selection shortcuts.
    _ = _KNOWN_UNIMPLEMENTED_DBMS
