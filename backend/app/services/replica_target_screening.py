"""R-01-B provisional replica-target identity screening (OFFLINE ONLY).

This is NOT an authorization / allowlist / site-attestation implementation.
It is intentionally not wired into Connection Profile APIs, DEMIS adapters,
Inspector, preview or query execution. A caller-supplied SiteTargetExpectation
is untrusted and can NEVER produce permission to connect.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.adapters.demis.profile import ConnectionProfileSnapshot


class SiteTargetPurpose(StrEnum):
    REPLICA_READ = "REPLICA_EMR_READ"
    OPERATING_EMR = "OPERATING_EMR"
    UNKNOWN = "UNKNOWN"


class ReplicaTargetScreeningCode(StrEnum):
    SITE_RECORD_MISSING = "SITE_RECORD_MISSING"
    SITE_PURPOSE_NOT_REPLICA_READ = "SITE_PURPOSE_NOT_REPLICA_READ"
    PROFILE_DISABLED = "PROFILE_DISABLED"
    PROFILE_TARGET_INCOMPLETE = "PROFILE_TARGET_INCOMPLETE"
    TARGET_IDENTITY_MISMATCH = "TARGET_IDENTITY_MISMATCH"
    STRUCTURAL_MATCH_UNVERIFIED = "STRUCTURAL_MATCH_UNVERIFIED"


@dataclass(frozen=True, slots=True)
class SiteTargetExpectation:
    """Provisional target metadata awaiting INDEPENDENT site/DBA validation.

    No credentials, approval flag, trust token, DNS lookup or license assertion.
    It is never safe to construct this directly from a request and treat
    a successful comparison as authority to connect.
    """

    purpose: SiteTargetPurpose
    profile_id: int
    source_name: str
    environment: str
    dbms_type: str
    host: str
    port: int
    database_name: str
    username: str


@dataclass(frozen=True, slots=True)
class ReplicaTargetScreeningResult:
    code: ReplicaTargetScreeningCode
    structurally_matching: bool
    # Deliberately no successful runtime authorization path. A separate
    # authenticated, verified, time-bound, revocable site gate is required.
    connection_authorized: bool = False


def screen_replica_read_target(
    profile: ConnectionProfileSnapshot,
    expectation: SiteTargetExpectation | None,
) -> ReplicaTargetScreeningResult:
    """Compare exact target identity, without DNS, sockets, secrets or I/O.

    No fuzzy matching, hostname aliasing, fallback targets or name-based
    inference of 'replica' role. All denied/mismatch results are sanitized.
    Even an exact match is *unverified* and connection_authorized is False.
    """
    def result(code: ReplicaTargetScreeningCode, match: bool = False) -> ReplicaTargetScreeningResult:
        return ReplicaTargetScreeningResult(code=code, structurally_matching=match)

    if expectation is None:
        return result(ReplicaTargetScreeningCode.SITE_RECORD_MISSING)
    if expectation.purpose != SiteTargetPurpose.REPLICA_READ:
        return result(ReplicaTargetScreeningCode.SITE_PURPOSE_NOT_REPLICA_READ)
    if not profile.enabled:
        return result(ReplicaTargetScreeningCode.PROFILE_DISABLED)
    if not all((
        profile.dbms_type, profile.host, profile.port,
        profile.database_name, profile.username,
    )):
        return result(ReplicaTargetScreeningCode.PROFILE_TARGET_INCOMPLETE)

    identity = (
        profile.profile_id,
        profile.source_name,
        profile.environment,
        profile.dbms_type,
        profile.host,
        profile.port,
        profile.database_name,
        profile.username,
    )
    expected = (
        expectation.profile_id,
        expectation.source_name,
        expectation.environment,
        expectation.dbms_type,
        expectation.host,
        expectation.port,
        expectation.database_name,
        expectation.username,
    )
    # Exact matching is conservative until a site-approved DNS/alias policy
    # exists. Not a hostname or network boundary enforcement mechanism.
    if identity != expected:
        return result(ReplicaTargetScreeningCode.TARGET_IDENTITY_MISMATCH)
    return result(ReplicaTargetScreeningCode.STRUCTURAL_MATCH_UNVERIFIED, match=True)
