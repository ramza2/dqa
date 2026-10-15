"""S-03-F PostgreSQL SIGKILL / WAL recovery acceptance on an isolated DB only.

The runner controls three separate Python processes:
  1. pytest: commit the baseline Snapshot + READY/WARNING Imports.
  2. writer: FLUSH an in-flight Snapshot + new READY activation + event,
     publish the marker, then intentionally NEVER COMMIT.
  3. pytest: after Docker SIGKILL/restart, verify committed data survived and
     the in-flight changes disappeared.

No db_session / db_client fixture (those may TRUNCATE an actual DB).
No clinical data, DEMIS/Oracle, production DB, automatic Catalog promotion.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.adapters.catalog.activation_errors import (
    CatalogActivationError,
    CatalogActivationErrorCode,
)
from app.core.config import get_settings
from app.models.catalog_active import CatalogActivationEvent, CatalogActiveRevision
from app.models.catalog_import import CatalogImportRevision
from app.models.schema_snapshot_revision import SchemaSnapshotRevision
from app.services.catalog_active import activate_catalog_revision, get_active_catalog
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.catalog_query import list_tables
from app.services.schema_snapshot_history import capture_snapshot_revision
from app.services.schema_snapshot_review import build_latest_snapshot_warning_candidate
from tests.catalog_package_fixtures import DEFAULT_SOURCE, build_package_zip
from tests.test_schema_snapshot_history import _base

pytestmark = pytest.mark.integration

if os.environ.get("DQA_S03F_ISOLATED_PG") != "1":
    pytest.skip("S-03-F requires a dedicated disposable PostgreSQL", allow_module_level=True)

SOURCE = "s03f_crash_fixture"
READY_A_FP = "s03f-ready-committed-a"
READY_B_FP = "s03f-ready-uncommitted-b"


def _make_factory():
    settings = get_settings()
    if (
        settings.app_env != "test"
        or settings.dqa_db_host != "127.0.0.1"
        or settings.dqa_db_port != 55441
        or settings.dqa_db_name != "dqa_s03f_disposable"
        or settings.dqa_db_user != "dqa_s03f_user"
    ):
        raise RuntimeError("S03F_REFUSED: PostgreSQL target is not dedicated disposable DB")
    engine = create_engine(
        settings.sqlalchemy_database_url,
        pool_pre_ping=True,
        future=True,
        connect_args={"connect_timeout": 3, "options": "-c statement_timeout=10000"},
    )
    with engine.connect() as conn:
        if conn.scalar(text("SELECT current_database()")) != "dqa_s03f_disposable":
            raise RuntimeError("S03F_REFUSED: database identity mismatch")
        if conn.scalar(text("SELECT current_user")) != "dqa_s03f_user":
            raise RuntimeError("S03F_REFUSED: role identity mismatch")
        for table in (
            "catalog_import_revisions",
            "catalog_active_revisions",
            "catalog_activation_events",
            "schema_snapshot_revisions",
        ):
            if conn.scalar(
                text("SELECT to_regclass(:name)"),
                {"name": "public." + table},
            ) is None:
                raise RuntimeError("S03F_REFUSED: required migration missing")
    return engine, sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(scope="module")
def factory():
    engine, sf = _make_factory()
    try:
        yield sf
    finally:
        engine.dispose()


def _imports(db):
    return db.scalars(
        select(CatalogImportRevision)
        .where(CatalogImportRevision.source_name == SOURCE)
        .order_by(CatalogImportRevision.id)
    ).all()


def _snapshots(db):
    return db.scalars(
        select(SchemaSnapshotRevision)
        .where(SchemaSnapshotRevision.source_name == SOURCE)
        .order_by(SchemaSnapshotRevision.id)
    ).all()


def _events(db):
    return db.scalars(
        select(CatalogActivationEvent)
        .where(CatalogActivationEvent.source_name == SOURCE)
        .order_by(CatalogActivationEvent.id)
    ).all()


def _assert_committed_baseline(db):
    snapshots = _snapshots(db)
    assert len(snapshots) == 1
    assert snapshots[0].previous_revision_id is None
    assert snapshots[0].diff_summary_json["status"] == "NO_BASELINE"

    rows = _imports(db)
    assert len(rows) == 2
    ready, warning = rows
    assert ready.package_readiness == "READY"
    assert ready.validation_status == "VALID"
    assert ready.schema_fingerprint == READY_A_FP
    assert warning.package_readiness == "WARNING"
    assert warning.validation_status == "VALID"
    assert ready.id != warning.id
    assert all(row.schema_fingerprint != READY_B_FP for row in rows)

    active = get_active_catalog(db, SOURCE)
    assert active.revision_id == ready.id
    assert active.package_readiness == "READY"
    assert active.schema_fingerprint == READY_A_FP
    assert [t.name for t in list_tables(db, SOURCE)[1].items] == ["T1"]

    events = _events(db)
    assert len(events) == 1
    assert events[0].activated_revision_id == ready.id
    assert events[0].previous_revision_id is None
    assert db.scalar(
        select(func.count())
        .select_from(CatalogActiveRevision)
        .where(CatalogActiveRevision.source_name == SOURCE)
    ) == 1
    return snapshots[0], ready, warning


def test_seed_committed_baseline_before_forced_shutdown(factory):
    with factory() as db:
        assert not _imports(db)
        assert not _snapshots(db)
        assert not _events(db)
        assert db.scalar(
            select(func.count())
            .select_from(CatalogActiveRevision)
            .where(CatalogActiveRevision.source_name == SOURCE)
        ) == 0

        snapshot = capture_snapshot_revision(
            db, _base(),
            source_name=SOURCE,
            captured_by="s03f-synthetic-operator",
            capture_request_id=uuid4(),
            expected_previous_revision_id=None,
        ).revision
        snapshot_id = snapshot.id
        db.commit()

    ready_bytes = build_package_zip(
        package_readiness="READY",
        source={**DEFAULT_SOURCE, "source_name": SOURCE},
        fingerprint=READY_A_FP,
    )
    with factory() as db:
        ready, created = import_catalog_package_bytes(ready_bytes, db)
        assert created
        activated = activate_catalog_revision(db, ready.id)
        assert activated.changed
        db.commit()

    with factory() as db:
        candidate = build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=snapshot_id,
        )
        assert candidate.package_readiness == "WARNING"
        assert candidate.preflight_status == "NOT_VERIFIED"
        assert candidate.activation_eligible is False
        warning, created = import_catalog_package_bytes(candidate.archive_bytes, db)
        assert created
        assert warning.archive_sha256 == candidate.archive_sha256
        db.commit()

    with factory() as db:
        _assert_committed_baseline(db)


def hold_uncommitted_changes_until_killed(marker_path: Path):
    """Independent writer process holds a fully flushed transaction open."""
    if marker_path.exists():
        raise RuntimeError("S03F_REFUSED: existing writer marker")
    engine, factory = _make_factory()
    try:
        with factory() as db:
            snapshot, ready_a, _warning = _assert_committed_baseline(db)

            changed = _base()
            changed.tables[0] = replace(
                changed.tables[0],
                table_comment="synthetic uncommitted metadata",
            )
            staged_snapshot = capture_snapshot_revision(
                db,
                changed,
                source_name=SOURCE,
                captured_by="s03f-synthetic-operator",
                capture_request_id=uuid4(),
                expected_previous_revision_id=snapshot.id,
            ).revision
            assert staged_snapshot.id is not None

            ready_b_bytes = build_package_zip(
                package_readiness="READY",
                source={**DEFAULT_SOURCE, "source_name": SOURCE},
                fingerprint=READY_B_FP,
            )
            staged_ready, created = import_catalog_package_bytes(ready_b_bytes, db)
            assert created and staged_ready.id != ready_a.id
            swap = activate_catalog_revision(db, staged_ready.id)
            assert swap.changed and swap.previous_revision_id == ready_a.id
            # Ensure INSERT/UPDATE/ActivationEvent are all sent to PostgreSQL,
            # but NEVER commit this transaction before the forced PG SIGKILL.
            db.flush()
            assert len(_snapshots(db)) == 2
            assert len(_imports(db)) == 3
            assert len(_events(db)) == 2
            assert get_active_catalog(db, SOURCE).revision_id == staged_ready.id

            marker_path.write_text("uncommitted_writes_flushed\n", encoding="utf-8")
            while True:
                time.sleep(1)
    finally:
        engine.dispose()


def test_after_sigkill_wal_recovery_preserves_only_committed_state(factory):
    # Only called by runner after postmaster start time has changed and the
    # same PG cluster system_identifier is observed across crash recovery.
    with factory() as db:
        snapshot, ready, warning = _assert_committed_baseline(db)
        candidate = build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=snapshot.id,
        )
        assert candidate.package_readiness == "WARNING"
        assert candidate.activation_eligible is False
        assert candidate.archive_sha256 == warning.archive_sha256

        duplicate, created = import_catalog_package_bytes(candidate.archive_bytes, db)
        assert created is False
        assert duplicate.id == warning.id
        db.commit()

    with factory() as db:
        with pytest.raises(CatalogActivationError) as err:
            activate_catalog_revision(db, warning.id)
        assert err.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
        db.rollback()

    with factory() as db:
        repeat = activate_catalog_revision(db, ready.id)
        assert repeat.changed is False
        db.commit()

    with factory() as db:
        _assert_committed_baseline(db)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "hold-uncommitted":
        raise SystemExit("usage: test_s03f_disposable_pg_crash.py hold-uncommitted <new-marker-path>")
    hold_uncommitted_changes_until_killed(Path(sys.argv[2]))
