"""S-03-A: source-scoped latest Snapshot -> v2 WARNING artifact, offline.

No Oracle, network, real DEMIS, Catalog import/activation or write DB.
"""
from __future__ import annotations

from hashlib import sha256

import pytest

from app.services import schema_snapshot_review as review
from app.services.catalog_package_validation import validate_catalog_package_bytes
from app.services.schema_snapshot_review import SnapshotReviewError
from tests.test_schema_snapshot_history import _capture
from tests.test_schema_snapshot_review import _history

SOURCE = "oracle_demis_mock"


@pytest.mark.parametrize("with_second,revision_id", [(False, 1), (True, 2)])
def test_latest_snapshot_builds_valid_nonactivatable_warning_zip(
    monkeypatch, with_second, revision_id
):
    db = _history(monkeypatch, with_second=with_second)
    before = len(db.rows)
    original = [
        (row.schema_fingerprint, row.diff_summary_json.copy(), row.snapshot_json.copy())
        for row in db.rows
    ]
    result = review.build_latest_snapshot_warning_candidate(
        db, source_name=SOURCE, revision_id=revision_id,
    )
    assert result.source_name == SOURCE
    assert result.revision_id == revision_id
    assert result.package_readiness == "WARNING"
    assert result.preflight_status == "NOT_VERIFIED"
    assert result.activation_eligible is False
    assert result.archive_sha256 == sha256(result.archive_bytes).hexdigest()

    parsed = validate_catalog_package_bytes(result.archive_bytes)
    assert parsed.source.source_name == SOURCE
    assert parsed.source.default_schema == "DEMIS_OWNER"
    assert parsed.schema_fingerprint == result.schema_fingerprint
    assert parsed.package_readiness == "WARNING"
    assert parsed.activation_eligible is False
    assert parsed.manifest_document["package_readiness"] == "WARNING"
    assert len(db.rows) == before
    assert [
        (row.schema_fingerprint, row.diff_summary_json, row.snapshot_json)
        for row in db.rows
    ] == original


def test_second_build_reuses_existing_snapshot_and_yields_identical_bytes(monkeypatch):
    db = _history(monkeypatch)
    first = review.build_latest_snapshot_warning_candidate(
        db, source_name=SOURCE, revision_id=1,
    )
    second = review.build_latest_snapshot_warning_candidate(
        db, source_name=SOURCE, revision_id=1,
    )
    assert first.archive_bytes == second.archive_bytes
    assert first.archive_sha256 == second.archive_sha256
    assert len(db.rows) == 1


def test_superseded_snapshot_fails_before_rebuilding_package(monkeypatch):
    db = _history(monkeypatch, with_second=True)

    original_builder = review.build_catalog_v2_candidate
    calls = 0

    def preview_only(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            pytest.fail("superseded Snapshot must not create export ZIP")
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(review, "build_catalog_v2_candidate", preview_only)
    with pytest.raises(SnapshotReviewError) as caught:
        review.build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=1,
        )
    assert caught.value.code == "SNAPSHOT_CANDIDATE_SUPERSEDED"
    assert calls == 1  # existing review preview verifies the v2 candidate


@pytest.mark.parametrize("source,revision_id", [("wrong_source", 1), (SOURCE, 999)])
def test_cross_source_and_missing_revision_fail_closed(monkeypatch, source, revision_id):
    db = _history(monkeypatch)
    with pytest.raises(SnapshotReviewError) as caught:
        review.build_latest_snapshot_warning_candidate(
            db, source_name=source, revision_id=revision_id,
        )
    assert caught.value.code == "SNAPSHOT_REVISION_NOT_FOUND"


@pytest.mark.parametrize("damage", ["fingerprint", "diff", "target", "snapshot"])
def test_stored_tampering_blocks_candidate_before_build(monkeypatch, damage):
    db = _history(monkeypatch)
    row = db.rows[0]
    if damage == "fingerprint":
        row.schema_fingerprint = "0" * 64
    elif damage == "diff":
        row.diff_summary_json["status"] = "COMPARED"
    elif damage == "target":
        row.schema_name = "WRONG_SCHEMA"
    else:
        row.snapshot_json["tables"][0]["table_comment"] = "PRIVATE_VALUE"

    # review-preview performs validation and aborts before the additional build.
    with pytest.raises(SnapshotReviewError) as caught:
        review.build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=1,
        )
    assert caught.value.code == "SNAPSHOT_REVIEW_UNVERIFIABLE"
    assert "PRIVATE_VALUE" not in str(caught.value)


def test_new_capture_during_candidate_build_invalidates_export(monkeypatch):
    db = _history(monkeypatch)
    original_builder = review.build_catalog_v2_candidate
    calls = 0

    def concurrent_builder(*args, **kwargs):
        nonlocal calls
        calls += 1
        # Preview's builder is called first. Emulate a concurrent capture
        # while the export's separate candidate generation is in progress.
        if calls == 2:
            newer = _capture(db, expected=1).revision
            newer.captured_at = db.rows[0].captured_at
        return original_builder(*args, **kwargs)

    monkeypatch.setattr(review, "build_catalog_v2_candidate", concurrent_builder)
    with pytest.raises(SnapshotReviewError) as caught:
        review.build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=1,
        )
    assert caught.value.code == "SNAPSHOT_CANDIDATE_SUPERSEDED"
    assert calls == 2
    assert len(db.rows) == 2


def test_changed_latest_fingerprint_during_export_blocks_result(monkeypatch):
    db = _history(monkeypatch)
    original_builder = review.build_catalog_v2_candidate
    calls = 0

    def corrupt_after_build(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = original_builder(*args, **kwargs)
        if calls == 2:
            db.rows[0].schema_fingerprint = "b" * 64
        return result

    monkeypatch.setattr(review, "build_catalog_v2_candidate", corrupt_after_build)
    with pytest.raises(SnapshotReviewError) as caught:
        review.build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=1,
        )
    assert caught.value.code == "SNAPSHOT_CANDIDATE_SUPERSEDED"


def test_bad_rebuilt_package_fails_sanitized_without_artifact(monkeypatch):
    db = _history(monkeypatch)
    original_builder = review.build_catalog_v2_candidate
    calls = 0

    def corrupt_export(*args, **kwargs):
        nonlocal calls
        calls += 1
        return b"not a valid ZIP; PRIVATE_SECRET" if calls == 2 else original_builder(*args, **kwargs)

    monkeypatch.setattr(review, "build_catalog_v2_candidate", corrupt_export)
    with pytest.raises(SnapshotReviewError) as caught:
        review.build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=1,
        )
    assert caught.value.code == "SNAPSHOT_CANDIDATE_UNVERIFIABLE"
    assert "PRIVATE_SECRET" not in str(caught.value)


def test_invalid_stored_timestamp_does_not_expose_detail(monkeypatch):
    db = _history(monkeypatch)
    db.rows[0].captured_at = db.rows[0].captured_at.replace(tzinfo=None)
    with pytest.raises(SnapshotReviewError) as caught:
        review.build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=1,
        )
    assert caught.value.code == "SNAPSHOT_REVIEW_UNVERIFIABLE"
