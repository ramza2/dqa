"""S-04-C-2B-2A: offline *shape/comparison* contract for proposed DBA evidence.

THIS MODULE NEVER CERTIFIES AN INDEPENDENT ISSUER OR MARKS PREFLIGHT VERIFIED.
No production evidence issuer, signature/identity trust policy, revocation or
durable replay protection has been approved. No route, DB writes or Oracle IO.
Providers are an abstract seam; a synthetic provider exists ONLY in tests.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hmac import compare_digest
from typing import Literal, Protocol
from uuid import UUID


REQUIRED_METADATA_CATEGORIES: frozenset[str] = frozenset({
    "tables", "columns", "primary_keys", "unique_constraints",
    "foreign_keys", "indexes",
})
_SOURCE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,254}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class SnapshotPreflightContext:
    """Internal, previously validated and database-derived Snapshot binding.

    The future caller MUST derive this from source-scoped immutable history
    plus S-04-C-2A integrity verification, never from client JSON.
    """

    source_name: str
    revision_id: int
    latest_revision_id: int
    schema_fingerprint: str
    db_type: str
    database_name: str
    schema_name: str
    captured_at: datetime
    snapshot_verified: bool


@dataclass(frozen=True)
class ProposedEvidenceEnvelope:
    """Untrusted independent-observation CLAIMS, not verified issuer proof."""

    evidence_id: UUID
    issuer_id: str
    source_name: str
    revision_id: int
    schema_fingerprint: str
    db_type: str
    database_name: str
    schema_name: str
    # Must originate from independently inspected metadata in a real provider.
    observed_fingerprint: str
    coverage: frozenset[str]
    omissions: tuple[str, ...]
    observed_at: datetime
    issued_at: datetime
    expires_at: datetime


class EvidenceProvider(Protocol):
    """Future external boundary. No trusted production implementation yet."""

    def fetch(self, context: SnapshotPreflightContext) -> ProposedEvidenceEnvelope:
        ...


class UnconfiguredEvidenceProvider:
    """Safe default: never read any network, credentials or patient data."""

    def fetch(self, context: SnapshotPreflightContext) -> ProposedEvidenceEnvelope:
        raise RuntimeError("trusted independent issuer is not configured")


PreflightReason = Literal[
    "NO_TRUSTED_PROVIDER",
    "INVALID_SNAPSHOT_CONTEXT",
    "SUPERSEDED_SNAPSHOT",
    "EVIDENCE_UNAVAILABLE",
    "INVALID_EVIDENCE",
    "TARGET_MISMATCH",
    "FINGERPRINT_MISMATCH",
    "INCOMPLETE_COVERAGE",
    "INVALID_EVIDENCE_TIME",
    "EVIDENCE_EXPIRED",
    "STRUCTURAL_MATCH_ONLY",
]


@dataclass(frozen=True)
class PreflightContractResult:
    reason_code: PreflightReason
    structural_match: bool
    preflight_status: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    independently_authenticated: Literal[False] = False
    replay_protected: Literal[False] = False
    revocation_checked: Literal[False] = False
    catalog_ready: Literal[False] = False
    activation_eligible: Literal[False] = False


def _result(code: PreflightReason, *, match: bool = False) -> PreflightContractResult:
    return PreflightContractResult(reason_code=code, structural_match=match)


def _utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return dt.astimezone(timezone.utc)


def _context_valid(value: SnapshotPreflightContext) -> bool:
    return (
        isinstance(value, SnapshotPreflightContext)
        and isinstance(value.source_name, str)
        and _SOURCE_RE.fullmatch(value.source_name) is not None
        and type(value.revision_id) is int
        and value.revision_id > 0
        and type(value.latest_revision_id) is int
        and value.latest_revision_id > 0
        and isinstance(value.schema_fingerprint, str)
        and _SHA256_RE.fullmatch(value.schema_fingerprint) is not None
        and value.db_type == "oracle"
        and isinstance(value.database_name, str)
        and bool(value.database_name.strip())
        and isinstance(value.schema_name, str)
        and bool(value.schema_name.strip())
        and value.snapshot_verified is True
    )


def check_preflight_evidence_contract(
    context: SnapshotPreflightContext,
    *,
    provider: EvidenceProvider | None = None,
    now: datetime | None = None,
) -> PreflightContractResult:
    """Check claimed source/target/digest/scope/time with fail-closed results.

    Even for a synthetic perfect match, status MUST stay NOT_VERIFIED.
    No trusted issuer authentication, revocation, durable replay prevention,
    policy approval or READY/activation transition is implemented here.
    """
    try:
        moment = _utc(now if now is not None else datetime.now(timezone.utc))
        if not _context_valid(context):
            return _result("INVALID_SNAPSHOT_CONTEXT")
        captured_at = _utc(context.captured_at)
    except (ValueError, TypeError, AttributeError):
        return _result("INVALID_SNAPSHOT_CONTEXT")

    if context.revision_id != context.latest_revision_id:
        return _result("SUPERSEDED_SNAPSHOT")

    if provider is None or isinstance(provider, UnconfiguredEvidenceProvider):
        return _result("NO_TRUSTED_PROVIDER")

    try:
        evidence = provider.fetch(context)
    except Exception:
        # No error, host, credential, unsigned body or stack trace leaks.
        return _result("EVIDENCE_UNAVAILABLE")

    if not isinstance(evidence, ProposedEvidenceEnvelope):
        return _result("INVALID_EVIDENCE")
    if (
        not isinstance(evidence.evidence_id, UUID)
        or not isinstance(evidence.issuer_id, str)
        or not evidence.issuer_id.strip()
        or evidence.issuer_id != evidence.issuer_id.strip()
        or len(evidence.issuer_id) > 255
        or type(evidence.revision_id) is not int
        or evidence.revision_id <= 0
        or not isinstance(evidence.schema_fingerprint, str)
        or _SHA256_RE.fullmatch(evidence.schema_fingerprint) is None
        or not isinstance(evidence.observed_fingerprint, str)
        or _SHA256_RE.fullmatch(evidence.observed_fingerprint) is None
    ):
        return _result("INVALID_EVIDENCE")

    if (
        evidence.source_name != context.source_name
        or evidence.revision_id != context.revision_id
        or evidence.db_type != context.db_type
        or evidence.database_name != context.database_name
        or evidence.schema_name != context.schema_name
    ):
        return _result("TARGET_MISMATCH")

    if (
        not compare_digest(evidence.schema_fingerprint, context.schema_fingerprint)
        or not compare_digest(evidence.observed_fingerprint, context.schema_fingerprint)
    ):
        return _result("FINGERPRINT_MISMATCH")

    if (
        not isinstance(evidence.coverage, frozenset)
        or evidence.coverage != REQUIRED_METADATA_CATEGORIES
        or not isinstance(evidence.omissions, tuple)
        or bool(evidence.omissions)
    ):
        return _result("INCOMPLETE_COVERAGE")

    try:
        observed_at = _utc(evidence.observed_at)
        issued_at = _utc(evidence.issued_at)
        expires_at = _utc(evidence.expires_at)
    except (ValueError, TypeError, AttributeError):
        return _result("INVALID_EVIDENCE_TIME")

    if (
        observed_at < captured_at
        or observed_at > issued_at
        or issued_at > moment
        or expires_at <= issued_at
    ):
        return _result("INVALID_EVIDENCE_TIME")

    if expires_at <= moment:
        return _result("EVIDENCE_EXPIRED")

    # This matches ONLY the proposed data contract. A fake test provider can
    # reach this branch but must never provide production issuer authority.
    return _result("STRUCTURAL_MATCH_ONLY", match=True)
