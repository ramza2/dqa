"""S-04-C-2B-2A: proposed evidence-contract tests; no DB, Oracle or sockets."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.services.schema_catalog_candidate import _fingerprint, _physical_payload
from app.services.schema_preflight_contract import (
    ProposedEvidenceEnvelope,
    REQUIRED_METADATA_CATEGORIES,
    SnapshotPreflightContext,
    UnconfiguredEvidenceProvider,
    check_preflight_evidence_contract,
)
from tests.mock_schema_preflight_provider import SyntheticEvidenceProvider
from tests.test_schema_snapshot_history import _base

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
CAPTURED = datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc)


def _context(snapshot=None):
    snapshot = snapshot or _base()
    return SnapshotPreflightContext(
        source_name="oracle_demis_mock",
        revision_id=9,
        latest_revision_id=9,
        schema_fingerprint=_fingerprint(_physical_payload(snapshot)),
        db_type=snapshot.db_type,
        database_name=snapshot.database_name,
        schema_name=snapshot.schema_name,
        captured_at=CAPTURED,
        snapshot_verified=True,
    )


def _provider():
    # This mock is constructed separately from the expected Snapshot.
    return SyntheticEvidenceProvider(independently_constructed_mock_snapshot=_base())


def _check(context=None, provider=None, now=NOW):
    return check_preflight_evidence_contract(
        context if context is not None else _context(),
        provider=provider, now=now,
    )


def test_match_never_authenticates_issuer_or_approves_ready():
    provider = _provider()
    result = _check(provider=provider)
    assert provider.calls == 1
    assert result.reason_code == "STRUCTURAL_MATCH_ONLY"
    assert result.structural_match is True
    assert result.preflight_status == "NOT_VERIFIED"
    assert result.independently_authenticated is False
    assert result.replay_protected is False
    assert result.revocation_checked is False
    assert result.catalog_ready is False
    assert result.activation_eligible is False


def test_no_provider_fail_closed_and_no_network():
    assert _check().reason_code == "NO_TRUSTED_PROVIDER"
    assert _check(provider=UnconfiguredEvidenceProvider()).reason_code == "NO_TRUSTED_PROVIDER"


def test_provider_exception_is_sanitized():
    provider = _provider()
    provider.fail = True
    result = _check(provider=provider)
    assert provider.calls == 1
    assert result.reason_code == "EVIDENCE_UNAVAILABLE"
    assert "private credential" not in str(result)
    assert result.preflight_status == "NOT_VERIFIED"


@pytest.mark.parametrize("changes", [
    {"source_name": "../bad"},
    {"revision_id": 0},
    {"revision_id": True},
    {"latest_revision_id": 0},
    {"schema_fingerprint": "bad"},
    {"db_type": "postgres"},
    {"database_name": " "},
    {"schema_name": ""},
    {"snapshot_verified": False},
    {"captured_at": datetime(2026, 10, 14, 10, 0)},
])
def test_invalid_snapshot_context_never_contacts_provider(changes):
    provider = _provider()
    context = replace(_context(), **changes)
    result = _check(context=context, provider=provider)
    assert result.reason_code == "INVALID_SNAPSHOT_CONTEXT"
    assert provider.calls == 0
    assert result.activation_eligible is False


def test_old_snapshot_never_contacts_provider():
    provider = _provider()
    context = replace(_context(), latest_revision_id=10)
    result = _check(context=context, provider=provider)
    assert result.reason_code == "SUPERSEDED_SNAPSHOT"
    assert provider.calls == 0


def test_separately_modified_observed_snapshot_mismatch():
    provider = _provider()
    changed = deepcopy(provider.independently_constructed_mock_snapshot)
    changed.tables[0] = replace(changed.tables[0], table_comment="synthetic different")
    provider.independently_constructed_mock_snapshot = changed
    result = _check(provider=provider)
    assert result.reason_code == "FINGERPRINT_MISMATCH"
    assert not result.structural_match


class ConstantProvider:
    def __init__(self, evidence):
        self.evidence = evidence

    def fetch(self, _context):
        return self.evidence


def _envelope(**changes):
    e = _provider().fetch(_context())
    return replace(e, **changes)


@pytest.mark.parametrize("changes", [
    {"source_name": "not-the-source"},
    {"revision_id": 8},
    {"db_type": "postgres"},
    {"database_name": "OTHERDB"},
    {"schema_name": "OTHER_SCHEMA"},
])
def test_evidence_target_mismatch(changes):
    result = _check(provider=ConstantProvider(_envelope(**changes)))
    assert result.reason_code == "TARGET_MISMATCH"


@pytest.mark.parametrize("changes", [
    {"schema_fingerprint": "b" * 64},
    {"observed_fingerprint": "b" * 64},
])
def test_evidence_digests_must_match(changes):
    result = _check(provider=ConstantProvider(_envelope(**changes)))
    assert result.reason_code == "FINGERPRINT_MISMATCH"


@pytest.mark.parametrize("changes", [
    {"coverage": frozenset({"tables", "columns"})},
    {"coverage": REQUIRED_METADATA_CATEGORIES - {"foreign_keys"}},
    {"coverage": REQUIRED_METADATA_CATEGORIES | {"clinical_rows"}},
    {"omissions": ("missing external FK",)},
    {"coverage": {"tables", "columns"}},
    {"omissions": ["missing index"]},
])
def test_scope_is_exact_and_omissions_fail_closed(changes):
    result = _check(provider=ConstantProvider(_envelope(**changes)))
    assert result.reason_code == "INCOMPLETE_COVERAGE"
    assert not result.structural_match


@pytest.mark.parametrize("changes,expected", [
    ({"observed_at": CAPTURED - timedelta(seconds=1)}, "INVALID_EVIDENCE_TIME"),
    ({"observed_at": NOW + timedelta(seconds=1)}, "INVALID_EVIDENCE_TIME"),
    ({"issued_at": NOW + timedelta(seconds=1)}, "INVALID_EVIDENCE_TIME"),
    ({"issued_at": CAPTURED}, "INVALID_EVIDENCE_TIME"),
    ({"expires_at": CAPTURED}, "INVALID_EVIDENCE_TIME"),
    ({"expires_at": NOW - timedelta(seconds=1)}, "EVIDENCE_EXPIRED"),
    ({"expires_at": NOW}, "EVIDENCE_EXPIRED"),
    ({"observed_at": datetime(2026, 10, 14, 10, 10)}, "INVALID_EVIDENCE_TIME"),
    ({"issued_at": datetime(2026, 10, 14, 10, 15)}, "INVALID_EVIDENCE_TIME"),
    ({"expires_at": datetime(2026, 10, 14, 12, 30)}, "INVALID_EVIDENCE_TIME"),
])
def test_time_boundaries(changes, expected):
    result = _check(provider=ConstantProvider(_envelope(**changes)))
    assert result.reason_code == expected
    assert result.preflight_status == "NOT_VERIFIED"


@pytest.mark.parametrize("changes", [
    {"evidence_id": "forged-id"},
    {"issuer_id": ""},
    {"issuer_id": " shady "},
    {"issuer_id": "a" * 256},
    {"revision_id": True},
    {"schema_fingerprint": "bad"},
    {"observed_fingerprint": "bad"},
    {"schema_fingerprint": None},
])
def test_invalid_untrusted_envelope(changes):
    result = _check(provider=ConstantProvider(_envelope(**changes)))
    assert result.reason_code == "INVALID_EVIDENCE"


def test_wrong_provider_type_is_rejected():
    result = _check(provider=ConstantProvider({"status": "VERIFIED"}))
    assert result.reason_code == "INVALID_EVIDENCE"


def test_client_claim_of_approval_cannot_be_injected():
    original = _envelope()
    assert not hasattr(original, "approved")
    assert not hasattr(original, "catalog_ready")
    assert not hasattr(original, "signed")
    assert not hasattr(original, "clinical_rows")
    result = _check(provider=ConstantProvider(original))
    assert result.structural_match
    assert not result.activation_eligible


def test_aware_offset_dates_normalize_to_utc():
    offset = timezone(timedelta(hours=9))
    evidence = _envelope(
        observed_at=datetime(2026, 10, 14, 19, 10, tzinfo=offset),
        issued_at=datetime(2026, 10, 14, 19, 15, tzinfo=offset),
        expires_at=datetime(2026, 10, 14, 21, 30, tzinfo=offset),
    )
    result = _check(provider=ConstantProvider(evidence))
    assert result.reason_code == "STRUCTURAL_MATCH_ONLY"
    assert result.preflight_status == "NOT_VERIFIED"


def test_missing_positive_policy_after_mock_success():
    evidence = _envelope(evidence_id=UUID("f1923caa-fc28-4126-831e-81473c83d3a6"))
    first = _check(provider=ConstantProvider(evidence))
    replay = _check(provider=ConstantProvider(evidence))
    assert first.structural_match is True
    assert replay.structural_match is True
    # No durable nonce registry or independently controlled trust store.
    # A repeated envelope is NEVER preflight-approved at this phase.
    assert replay.replay_protected is False
    assert replay.preflight_status == "NOT_VERIFIED"
    assert replay.catalog_ready is False
