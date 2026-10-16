"""R-01-C site evidence draft contract: synthetic and DB-free."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.services.replica_target_screening import SiteTargetExpectation, SiteTargetPurpose
from app.services.site_target_evidence_review import (
    SiteEvidenceReviewCode as Code,
    SiteEvidenceReviewResult,
    SiteTargetEvidenceDraft,
    review_site_target_evidence,
)

NOW = datetime(2026, 10, 16, 3, 0, tzinfo=timezone.utc)


def _profile(**changes: Any) -> ConnectionProfileSnapshot:
    values: dict[str, Any] = {
        "profile_id": 41,
        "name": "Synthetic read replica",
        "source_name": "synthetic_replica",
        "environment": "sandbox",
        "enabled": True,
        "dbms_type": "oracle",
        "host": "replica.invalid",
        "port": 1521,
        "database_name": "SYNTHETIC_DB",
        "username": "synthetic_ro",
        "credential_secret_ref": "env:SYNTHETIC_NO_SECRET",
    }
    values.update(changes)
    return ConnectionProfileSnapshot.model_validate(values)


def _target(**changes: Any) -> SiteTargetExpectation:
    values: dict[str, Any] = {
        "purpose": SiteTargetPurpose.REPLICA_READ,
        "profile_id": 41,
        "source_name": "synthetic_replica",
        "environment": "sandbox",
        "dbms_type": "oracle",
        "host": "replica.invalid",
        "port": 1521,
        "database_name": "SYNTHETIC_DB",
        "username": "synthetic_ro",
    }
    values.update(changes)
    return SiteTargetExpectation(**values)


def _evidence(**changes: Any) -> SiteTargetEvidenceDraft:
    values: dict[str, Any] = {
        "evidence_id": "site-doc-synthetic-001",
        "issuer_id": "untrusted-stub-issuer",
        "key_id": "untrusted-stub-key",
        "target": _target(),
        "issued_at": NOW - timedelta(hours=2),
        "not_before": NOW - timedelta(hours=1),
        "expires_at": NOW + timedelta(hours=1),
        "signature": b"forged-not-a-verified-signature",
        "declared_revoked": False,
    }
    values.update(changes)
    return SiteTargetEvidenceDraft(**values)


def _review(
    evidence: SiteTargetEvidenceDraft | None = None,
    *,
    profile: ConnectionProfileSnapshot | None = None,
    now: datetime = NOW,
) -> SiteEvidenceReviewResult:
    return review_site_target_evidence(profile or _profile(), evidence, now=now)


def _denied(verdict: SiteEvidenceReviewResult, code: Code) -> None:
    assert verdict.code == code
    assert verdict.connection_authorized is False
    assert verdict.cryptographically_verified is False


def test_perfect_claims_have_no_trust_or_connection_authority() -> None:
    verdict = _review(_evidence())
    assert verdict.claims_consistent
    _denied(verdict, Code.CLAIMS_MATCH_UNTRUSTED)


def test_missing_evidence_fails_closed() -> None:
    _denied(_review(), Code.EVIDENCE_MISSING)


@pytest.mark.parametrize("clock", [
    datetime(2026, 10, 16, 3, 0),
    None,
])
def test_invalid_explicit_clock(clock: datetime | None) -> None:
    _denied(_review(_evidence(), now=clock), Code.CLOCK_INVALID)  # type: ignore[arg-type]


@pytest.mark.parametrize("field,bad", [
    ("evidence_id", ""),
    ("issuer_id", "  "),
    ("key_id", ""),
    ("signature", b""),
    ("signature", "fake-not-bytes"),
    ("target", None),
])
def test_incomplete_envelope_is_not_trusted(field: str, bad: Any) -> None:
    _denied(_review(_evidence(**{field: bad})), Code.EVIDENCE_INCOMPLETE)


@pytest.mark.parametrize("purpose", [
    SiteTargetPurpose.OPERATING_EMR,
    SiteTargetPurpose.UNKNOWN,
])
def test_original_or_unknown_target_explicitly_rejected(purpose: SiteTargetPurpose) -> None:
    _denied(
        _review(_evidence(target=_target(purpose=purpose))),
        Code.PURPOSE_NOT_REPLICA,
    )


@pytest.mark.parametrize("field,bad", [
    ("profile_id", 42),
    ("source_name", "synthetic_operating"),
    ("environment", "production"),
    ("host", "operating.invalid"),
    ("database_name", "OTHER_DB"),
    ("username", "different_reader"),
])
def test_target_binding_mismatch_is_rejected(field: str, bad: Any) -> None:
    _denied(
        _review(_evidence(target=_target(**{field: bad}))),
        Code.PROFILE_TARGET_NOT_MATCHED,
    )


def test_disabled_profile_fails_target_screening() -> None:
    _denied(
        _review(_evidence(), profile=_profile(enabled=False)),
        Code.PROFILE_TARGET_NOT_MATCHED,
    )


@pytest.mark.parametrize("field", ["issued_at", "not_before", "expires_at"])
def test_timezone_naive_evidence_timestamp_fails(field: str) -> None:
    _denied(
        _review(_evidence(**{field: NOW.replace(tzinfo=None)})),
        Code.VALIDITY_WINDOW_INVALID,
    )


@pytest.mark.parametrize("changes", [
    {"not_before": NOW + timedelta(hours=2), "expires_at": NOW + timedelta(hours=1)},
    {"not_before": NOW + timedelta(hours=1), "expires_at": NOW + timedelta(hours=1)},
    {"issued_at": NOW + timedelta(hours=2), "expires_at": NOW + timedelta(hours=1)},
])
def test_bad_timestamp_order_fails(changes: dict[str, datetime]) -> None:
    _denied(
        _review(_evidence(**changes)),
        Code.VALIDITY_WINDOW_INVALID,
    )


def test_declared_revoked_is_rejected_but_false_is_not_proof_of_nonrevocation() -> None:
    _denied(_review(_evidence(declared_revoked=True)), Code.DECLARED_REVOKED)
    _denied(_review(_evidence(declared_revoked=False)), Code.CLAIMS_MATCH_UNTRUSTED)


@pytest.mark.parametrize("changes", [
    {"issued_at": NOW + timedelta(minutes=1)},
    {"not_before": NOW + timedelta(minutes=1)},
])
def test_not_yet_valid_fails(changes: dict[str, datetime]) -> None:
    _denied(_review(_evidence(**changes)), Code.EVIDENCE_NOT_YET_VALID)


@pytest.mark.parametrize("now", [
    NOW + timedelta(hours=1),
    NOW + timedelta(days=1),
])
def test_expired_including_exact_boundary(now: datetime) -> None:
    _denied(_review(_evidence(), now=now), Code.EVIDENCE_EXPIRED)


def test_equivalent_timezone_is_not_auto_approval() -> None:
    plus_nine = timezone(timedelta(hours=9))
    verdict = _review(_evidence(), now=NOW.astimezone(plus_nine))
    _denied(verdict, Code.CLAIMS_MATCH_UNTRUSTED)
    assert verdict.claims_consistent is True


def test_fake_issuer_key_and_signature_never_become_trust() -> None:
    forged = _evidence(
        issuer_id="military-authority-CLAIM_ONLY",
        key_id="fake-root-key",
        signature=b"looks-real-but-not-verified",
    )
    verdict = _review(forged)
    _denied(verdict, Code.CLAIMS_MATCH_UNTRUSTED)


def test_result_authorization_cannot_be_constructed_or_overridden() -> None:
    verdict = _review(_evidence())
    with pytest.raises(FrozenInstanceError):
        verdict.code = Code.EVIDENCE_MISSING  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        verdict.connection_authorized = True  # type: ignore[misc]
    with pytest.raises(TypeError):
        replace(verdict, connection_authorized=True)


def test_no_socket_dns_or_credential_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    import socket

    forbidden = Mock(side_effect=AssertionError("network access forbidden"))
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    verdict = _review(_evidence())
    _denied(verdict, Code.CLAIMS_MATCH_UNTRUSTED)
    forbidden.assert_not_called()


def test_result_representation_excludes_site_identifiers_and_signature() -> None:
    signed = _evidence(
        target=_target(host="sensitive-original-host.invalid"),
        signature=b"sensitive-signature-placeholder",
    )
    verdict = _review(signed)
    _denied(verdict, Code.PROFILE_TARGET_NOT_MATCHED)
    assert "sensitive-original-host.invalid" not in repr(verdict)
    assert "sensitive-signature-placeholder" not in repr(verdict)
    assert "sensitive-original-host.invalid" not in repr(signed)
    assert "sensitive-signature-placeholder" not in repr(signed)
