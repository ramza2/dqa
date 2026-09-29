"""Production factory for ReadOnlyDemisAdapter — fail-closed without concrete DBMS."""

from __future__ import annotations

from app.adapters.demis.credentials import CredentialMaterial, CredentialResolver
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.adapters.demis.protocol import ReadOnlyDemisAdapter

# Explicitly rejected adapter kinds that must never be selected in production.
_FORBIDDEN_PRODUCTION_KINDS = frozenset({"fake", "test", "mock", "memory"})

# Concrete DEMIS adapter registry. Empty until DBMS/driver requirements confirm
# an implementation. Recognition of a label is not the same as support.
_REGISTERED_CONCRETE_DBMS: frozenset[str] = frozenset()


def create_readonly_demis_adapter(
    profile: ConnectionProfileSnapshot,
    *,
    credential_resolver: CredentialResolver,
) -> ReadOnlyDemisAdapter:
    """Build a live-capable read-only DEMIS adapter from a validated profile.

    Fail-closed rules for this foundation:
    - disabled profiles are rejected
    - required non-secret target metadata must be present
    - ``credential_secret_ref`` presence is required at profile validation
    - credentials are resolved only after a concrete adapter is selected
    - no concrete DBMS driver is registered yet → ``UNSUPPORTED_DBMS``
      (without calling ``CredentialResolver.resolve``)
    - fake/test adapters are never selectable through this factory
    - never falls back to DQA PostgreSQL / psycopg
    """
    _validate_profile_eligibility(profile)

    dbms = _normalize_dbms_type(profile.dbms_type)
    if dbms in _FORBIDDEN_PRODUCTION_KINDS:
        raise DemisAdapterError(
            DemisAdapterErrorCode.UNSUPPORTED_DBMS,
            "test/fake DEMIS adapters cannot be selected through the production factory",
        )

    if not _is_concrete_adapter_registered(dbms):
        # Fail closed before any secret access — do not use DQA DB.
        raise DemisAdapterError(
            DemisAdapterErrorCode.UNSUPPORTED_DBMS,
            "no concrete DEMIS read-only adapter is registered for the configured DBMS; "
            "blocked until DEMIS DBMS/driver requirements are confirmed",
        )

    # Reachable only after a concrete adapter exists for ``dbms``.
    material = _resolve_credentials(
        credential_resolver, profile.credential_secret_ref or ""
    )
    return _build_registered_adapter(dbms, profile, material)


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


def _normalize_dbms_type(dbms_type: str | None) -> str:
    return (dbms_type or "").strip().casefold()


def _is_concrete_adapter_registered(dbms: str) -> bool:
    """Minimal support check: true only when a concrete driver is registered."""
    if not dbms:
        return False
    return dbms in _REGISTERED_CONCRETE_DBMS


def _resolve_credentials(
    credential_resolver: CredentialResolver, credential_secret_ref: str
) -> CredentialMaterial:
    try:
        material = credential_resolver.resolve(credential_secret_ref)
    except DemisAdapterError:
        raise
    except Exception as exc:  # pragma: no cover - defensive sanitization
        raise DemisAdapterError(
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
            "credential reference could not be resolved",
        ) from exc

    if not material.get_secret():
        raise DemisAdapterError(
            DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
            "credential reference resolved to empty material",
        )
    return material


def _build_registered_adapter(
    dbms: str,
    profile: ConnectionProfileSnapshot,
    material: CredentialMaterial,
) -> ReadOnlyDemisAdapter:
    """Construct a registered concrete adapter.

    Unreachable while ``_REGISTERED_CONCRETE_DBMS`` is empty. Kept so credential
    resolution stays behind a real adapter selection gate.
    """
    # material/profile retained for future driver wiring; never log secrets.
    _ = (dbms, profile, material)
    raise DemisAdapterError(
        DemisAdapterErrorCode.UNSUPPORTED_DBMS,
        "no concrete DEMIS read-only adapter is registered for the configured DBMS; "
        "blocked until DEMIS DBMS/driver requirements are confirmed",
    )
