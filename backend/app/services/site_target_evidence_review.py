"""R-01-C offline site-target evidence *draft review*, never authorization.

Site issuer, key verification, independently checked revocation and actual
replica identity are DEC-10 pending. This module is NOT wired to any runtime
adapter, Connection Profile management, Inspector, Query or MCP endpoint.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum

from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.services.replica_target_screening import (
    ReplicaTargetScreeningCode,
    SiteTargetExpectation,
    SiteTargetPurpose,
    screen_replica_read_target,
)


class SiteEvidenceReviewCode(StrEnum):
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    CLOCK_INVALID = "CLOCK_INVALID"
    EVIDENCE_INCOMPLETE = "EVIDENCE_INCOMPLETE"
    PURPOSE_NOT_REPLICA = "PURPOSE_NOT_REPLICA"
    PROFILE_TARGET_NOT_MATCHED = "PROFILE_TARGET_NOT_MATCHED"
    VALIDITY_WINDOW_INVALID = "VALIDITY_WINDOW_INVALID"
    DECLARED_REVOKED = "DECLARED_REVOKED"
    EVIDENCE_NOT_YET_VALID = "EVIDENCE_NOT_YET_VALID"
    EVIDENCE_EXPIRED = "EVIDENCE_EXPIRED"
    CLAIMS_MATCH_UNTRUSTED = "CLAIMS_MATCH_UNTRUSTED"


@dataclass(frozen=True, slots=True, repr=False)
class SiteTargetEvidenceDraft:
    """UNTRUSTED prospective evidence envelope, NEVER a verified attestation.

    Signature bytes are a placeholder only; no key-store or issuer trust exists.
    An attacker may forge every field, including target, issuer, timestamps and
    a purported signature. declared_revoked=False says nothing about the
    authoritative revocation state; independent verification is required.
    """

    evidence_id: str
    issuer_id: str
    key_id: str
    target: SiteTargetExpectation = field(repr=False)
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    signature: bytes = field(repr=False)
    declared_revoked: bool = False


@dataclass(frozen=True, slots=True)
class SiteEvidenceReviewResult:
    code: SiteEvidenceReviewCode
    claims_consistent: bool

    @property
    def connection_authorized(self) -> bool:
        """Not configurable by callers: all evidence remains untrusted."""
        return False

    @property
    def cryptographically_verified(self) -> bool:
        """No issuer/key/trust store configured or used."""
        return False


def _aware(value: object) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def review_site_target_evidence(
    profile: ConnectionProfileSnapshot,
    evidence: SiteTargetEvidenceDraft | None,
    *,
    now: datetime,
) -> SiteEvidenceReviewResult:
    """Check *only* shape, time and R-01-B target consistency.

    No network/DB/secret resolution, key lookup, cryptographic verification
    or approval-issuer trust. Even CLAIMS_MATCH_UNTRUSTED denies connection.
    The clock is explicitly supplied for deterministic synthetic tests.
    """

    def result(code: SiteEvidenceReviewCode, match: bool = False) -> SiteEvidenceReviewResult:
        return SiteEvidenceReviewResult(code, claims_consistent=match)

    if evidence is None:
        return result(SiteEvidenceReviewCode.EVIDENCE_MISSING)
    if not _aware(now):
        return result(SiteEvidenceReviewCode.CLOCK_INVALID)
    if (
        not isinstance(evidence.evidence_id, str)
        or not evidence.evidence_id.strip()
        or not isinstance(evidence.issuer_id, str)
        or not evidence.issuer_id.strip()
        or not isinstance(evidence.key_id, str)
        or not evidence.key_id.strip()
        or not isinstance(evidence.signature, bytes)
        or not evidence.signature
        or not isinstance(evidence.target, SiteTargetExpectation)
    ):
        return result(SiteEvidenceReviewCode.EVIDENCE_INCOMPLETE)

    if evidence.target.purpose != SiteTargetPurpose.REPLICA_READ:
        return result(SiteEvidenceReviewCode.PURPOSE_NOT_REPLICA)

    screening = screen_replica_read_target(profile, evidence.target)
    if screening.code != ReplicaTargetScreeningCode.STRUCTURAL_MATCH_UNVERIFIED:
        return result(SiteEvidenceReviewCode.PROFILE_TARGET_NOT_MATCHED)

    if not all(_aware(t) for t in (evidence.issued_at, evidence.not_before, evidence.expires_at)):
        return result(SiteEvidenceReviewCode.VALIDITY_WINDOW_INVALID)

    issued_at = evidence.issued_at.astimezone(timezone.utc)
    not_before = evidence.not_before.astimezone(timezone.utc)
    expires_at = evidence.expires_at.astimezone(timezone.utc)
    current = now.astimezone(timezone.utc)

    if not_before >= expires_at or issued_at >= expires_at:
        return result(SiteEvidenceReviewCode.VALIDITY_WINDOW_INVALID)
    if evidence.declared_revoked:
        return result(SiteEvidenceReviewCode.DECLARED_REVOKED)
    if current < not_before or current < issued_at:
        return result(SiteEvidenceReviewCode.EVIDENCE_NOT_YET_VALID)
    if current >= expires_at:
        return result(SiteEvidenceReviewCode.EVIDENCE_EXPIRED)

    # NO positive trust verdict exists. A structurally and temporally coherent
    # self-asserted statement is not a military/DBA-approved replica target.
    return result(SiteEvidenceReviewCode.CLAIMS_MATCH_UNTRUSTED, match=True)
