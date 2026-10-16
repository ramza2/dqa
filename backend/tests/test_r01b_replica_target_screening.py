"""R-01-B offline-only identity-screening regression (synthetic metadata).

Never connects to Oracle/DEMIS, DNS, a secret resolver, Docker or the DQA DB.
A positive structural match is *not* an approval or runtime connect permit.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import Mock

import pytest

from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.services.replica_target_screening import (
    ReplicaTargetScreeningCode as Code,
    SiteTargetExpectation,
    SiteTargetPurpose,
    screen_replica_read_target,
)

SOURCE = "replicated_emr_synthetic"
ENV = "sandbox"
HOST = "synthetic-replica.invalid"


def profile(**changes: Any) -> ConnectionProfileSnapshot:
    values: dict[str, Any] = {
        "profile_id": 41,
        "name": "Synthetic replica read",
        "source_name": SOURCE,
        "environment": ENV,
        "enabled": True,
        "dbms_type": "oracle",
        "host": HOST,
        "port": 1521,
        "database_name": "MOCK_REPLICA",
        "username": "synthetic_reader",
        "credential_secret_ref": "env:SYNTHETIC_REPLICA_SECRET",
    }
    values.update(changes)
    return ConnectionProfileSnapshot.model_validate(values)


def expected(**changes: Any) -> SiteTargetExpectation:
    values: dict[str, Any] = {
        "purpose": SiteTargetPurpose.REPLICA_READ,
        "profile_id": 41,
        "source_name": SOURCE,
        "environment": ENV,
        "dbms_type": "oracle",
        "host": HOST,
        "port": 1521,
        "database_name": "MOCK_REPLICA",
        "username": "synthetic_reader",
    }
    values.update(changes)
    return SiteTargetExpectation(**values)


def check(
    subject: ConnectionProfileSnapshot | None = None,
    record: SiteTargetExpectation | None = None,
):
    return screen_replica_read_target(subject or profile(), record)


def test_matching_reference_is_only_structural_never_connection_authority() -> None:
    verdict = check(record=expected())
    assert verdict.code == Code.STRUCTURAL_MATCH_UNVERIFIED
    assert verdict.structurally_matching is True
    assert verdict.connection_authorized is False


def test_missing_site_record_denies_even_enabled_oracle_replica_label() -> None:
    verdict = check()
    assert verdict.code == Code.SITE_RECORD_MISSING
    assert verdict.structurally_matching is False
    assert verdict.connection_authorized is False


@pytest.mark.parametrize("purpose", [SiteTargetPurpose.OPERATING_EMR, SiteTargetPurpose.UNKNOWN])
def test_explicit_operating_or_unknown_target_is_never_matching(
    purpose: SiteTargetPurpose,
) -> None:
    verdict = check(record=expected(purpose=purpose))
    assert verdict.code == Code.SITE_PURPOSE_NOT_REPLICA_READ
    assert verdict.connection_authorized is False


def test_disabled_profile_is_blocked_before_identity_compare() -> None:
    verdict = check(profile(enabled=False), expected())
    assert verdict.code == Code.PROFILE_DISABLED
    assert verdict.connection_authorized is False


@pytest.mark.parametrize("field", [
    "dbms_type", "host", "port", "database_name", "username",
])
def test_incomplete_profile_target_fails_closed(field: str) -> None:
    verdict = check(profile(**{field: None}), expected())
    assert verdict.code == Code.PROFILE_TARGET_INCOMPLETE
    assert verdict.structurally_matching is False
    assert verdict.connection_authorized is False


@pytest.mark.parametrize("field,other", [
    ("profile_id", 42),
    ("source_name", "operating_emr_synthetic"),
    ("environment", "production"),
    ("dbms_type", "mysql"),
    ("host", "operating-emr.invalid"),
    ("port", 1522),
    ("database_name", "MOCK_ORIGINAL"),
    ("username", "another_reader"),
])
def test_identity_field_mismatch_never_accepted(field: str, other: Any) -> None:
    verdict = check(record=expected(**{field: other}))
    assert verdict.code == Code.TARGET_IDENTITY_MISMATCH
    assert verdict.structurally_matching is False
    assert verdict.connection_authorized is False


@pytest.mark.parametrize("host", ["synthetic-replica.invalid.", "SYNTHETIC-REPLICA.INVALID"])
def test_dns_alias_or_case_is_not_inferred(host: str) -> None:
    verdict = check(record=expected(host=host))
    assert verdict.code == Code.TARGET_IDENTITY_MISMATCH
    assert verdict.connection_authorized is False


def test_role_is_from_expected_record_not_host_name() -> None:
    impostor = profile(host="replica-looking-name.invalid")
    record = expected(host="replica-looking-name.invalid", purpose=SiteTargetPurpose.OPERATING_EMR)
    verdict = check(impostor, record)
    assert verdict.code == Code.SITE_PURPOSE_NOT_REPLICA_READ
    assert verdict.connection_authorized is False


def test_untrusted_self_asserted_site_record_does_not_grant_access() -> None:
    # Even if an attacker/caller fabricates a perfectly matching expectation,
    # comparison never issues a trusted authorization decision.
    forged = replace(expected(), purpose=SiteTargetPurpose.REPLICA_READ)
    verdict = check(record=forged)
    assert verdict.structurally_matching
    assert verdict.connection_authorized is False


def test_secret_rotation_does_not_make_comparison_a_credential_verification() -> None:
    verdict = check(
        profile(credential_secret_ref="env:ROTATED_SYNTHETIC_SECRET"),
        expected(),
    )
    assert verdict.code == Code.STRUCTURAL_MATCH_UNVERIFIED
    assert verdict.connection_authorized is False


def test_no_network_dns_adapter_or_credential_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    forbidden = Mock(side_effect=AssertionError("network/DNS prohibited"))
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    result = check(record=expected())
    assert result.code == Code.STRUCTURAL_MATCH_UNVERIFIED
    forbidden.assert_not_called()


def test_mismatch_error_never_echoes_target_metadata_or_secret() -> None:
    record = expected(host="sensitive-original-host.invalid")
    verdict = check(record=record)
    description = repr(verdict)
    for secret in ("sensitive-original-host.invalid", HOST, "env:SYNTHETIC_REPLICA_SECRET"):
        assert secret not in description
    assert verdict.connection_authorized is False
