"""S-03-E graceful PostgreSQL restart durability, disposable DB only.

The runner executes the two tests in separate Python processes, on opposite
sides of a real Compose container restart. No db_session fixture or TRUNCATE.
Only synthetic physical metadata; no Oracle/DEMIS, LLM, or clinical data.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.adapters.catalog.activation_errors import (
    CatalogActivationError, CatalogActivationErrorCode,
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

if os.environ.get("DQA_S03E_ISOLATED_PG") != "1":
    pytest.skip("S-03-E requires explicitly isolated PostgreSQL", allow_module_level=True)

SOURCE = "s03e_restart_fixture"
ROLLED_BACK_SOURCE = "s03e_rollback_fixture"
READY_FP = "s03e-ready-revision-001"


@pytest.fixture(scope="module")
def factory():
    cfg = get_settings()
    assert (
        cfg.app_env == "test"
        and cfg.dqa_db_host == "127.0.0.1"
        and cfg.dqa_db_port == 55440
        and cfg.dqa_db_name == "dqa_s03e_disposable"
        and cfg.dqa_db_user == "dqa_s03e_user"
    ), "refusing PostgreSQL acceptance outside dedicated S-03-E DB"

    engine = create_engine(
        cfg.sqlalchemy_database_url,
        pool_pre_ping=True, future=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=10000",
        },
    )
    try:
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT current_database()")) == "dqa_s03e_disposable"
            assert conn.scalar(text("SELECT current_user")) == "dqa_s03e_user"
            for table in (
                "catalog_import_revisions",
                "catalog_active_revisions",
                "catalog_activation_events",
                "schema_snapshot_revisions",
            ):
                assert conn.scalar(
                    text("SELECT to_regclass(:table)"), {"table": "public." + table},
                ) is not None
        yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    finally:
        engine.dispose()


def _active_and_history(db):
    active = get_active_catalog(db, SOURCE)
    tables = [t.name for t in list_tables(db, SOURCE)[1].items]
    events = db.scalars(
        select(CatalogActivationEvent)
        .where(CatalogActivationEvent.source_name == SOURCE)
        .order_by(CatalogActivationEvent.id)
    ).all()
    return active, tables, events


def _imports(db, source=SOURCE):
    return db.scalars(
        select(CatalogImportRevision)
        .where(CatalogImportRevision.source_name == source)
        .order_by(CatalogImportRevision.id)
    ).all()


def _snapshot_rows(db):
    return db.scalars(
        select(SchemaSnapshotRevision)
        .where(SchemaSnapshotRevision.source_name == SOURCE)
        .order_by(SchemaSnapshotRevision.id)
    ).all()


def test_before_restart_commit_snapshot_ready_warning_and_rollback_other(factory):
    with factory() as db:
        assert not _imports(db)
        assert not _snapshot_rows(db)
        assert db.scalar(select(func.count()).select_from(CatalogActiveRevision)) == 0

        snapshot = capture_snapshot_revision(
            db, _base(),
            source_name=SOURCE,
            captured_by="s03e-synthetic-operator",
            capture_request_id=uuid4(),
            expected_previous_revision_id=None,
        ).revision
        snapshot_id = snapshot.id
        db.commit()

    ready_archive = build_package_zip(
        source={**DEFAULT_SOURCE, "source_name": SOURCE},
        fingerprint=READY_FP,
        package_readiness="READY",
    )
    with factory() as db:
        ready, created = import_catalog_package_bytes(ready_archive, db)
        assert created
        ready_id = ready.id
        activation = activate_catalog_revision(db, ready_id)
        assert activation.changed
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
        warning_id = warning.id
        assert warning.schema_fingerprint == candidate.schema_fingerprint
        db.commit()

    # Deliberately abort an unrelated import BEFORE restart. The rollback
    # record must not appear after PostgreSQL restarts.
    rolled_back_archive = build_package_zip(
        source={**DEFAULT_SOURCE, "source_name": ROLLED_BACK_SOURCE},
        fingerprint="s03e-rolled-back",
        package_readiness="WARNING",
    )
    with factory() as db:
        staged, created = import_catalog_package_bytes(rolled_back_archive, db)
        assert created and staged.id is not None
        db.rollback()

    with factory() as db:
        snapshots = _snapshot_rows(db)
        assert len(snapshots) == 1
        assert snapshots[0].id == snapshot_id
        assert snapshots[0].schema_fingerprint == candidate.schema_fingerprint
        assert snapshots[0].diff_summary_json["status"] == "NO_BASELINE"
        imports = _imports(db)
        assert len(imports) == 2
        assert [r.id for r in imports] == [ready_id, warning_id]
        assert [r.package_readiness for r in imports] == ["READY", "WARNING"]
        assert imports[1].archive_sha256 == candidate.archive_sha256
        assert not _imports(db, ROLLED_BACK_SOURCE)
        active, tables, events = _active_and_history(db)
        assert active.revision_id == ready_id
        assert active.schema_fingerprint == READY_FP
        assert tables == ["T1"]
        assert len(events) == 1
        assert events[0].activated_revision_id == ready_id
        assert events[0].previous_revision_id is None


def test_after_restart_committed_rows_survive_retry_and_warning_stays_inactive(factory):
    # This runs in another Python process, only after the runner validates
    # that pg_postmaster_start_time has changed after Compose restart.
    with factory() as db:
        snapshots = _snapshot_rows(db)
        assert len(snapshots) == 1
        snapshot = snapshots[0]
        assert snapshot.diff_summary_json["status"] == "NO_BASELINE"
        imports = _imports(db)
        assert len(imports) == 2
        ready, warning = imports
        assert ready.package_readiness == "READY"
        assert ready.schema_fingerprint == READY_FP
        assert warning.package_readiness == "WARNING"
        assert warning.validation_status == "VALID"
        assert warning.archive_sha256 != ready.archive_sha256
        assert not _imports(db, ROLLED_BACK_SOURCE)

        active, tables, events = _active_and_history(db)
        assert active.revision_id == ready.id
        assert active.schema_fingerprint == READY_FP
        assert tables == ["T1"]
        assert len(events) == 1
        assert events[0].activated_revision_id == ready.id
        assert events[0].previous_revision_id is None

        # Reconstruct ZIP from the persisted Snapshot after restart; a matching
        # SHA proves the same immutable candidate and Import deduplication.
        regenerated = build_latest_snapshot_warning_candidate(
            db, source_name=SOURCE, revision_id=snapshot.id,
        )
        assert regenerated.package_readiness == "WARNING"
        assert regenerated.archive_sha256 == warning.archive_sha256
        same, created = import_catalog_package_bytes(regenerated.archive_bytes, db)
        assert created is False
        assert same.id == warning.id
        db.commit()

    with factory() as db:
        with pytest.raises(CatalogActivationError) as caught:
            activate_catalog_revision(db, warning.id)
        assert caught.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
        db.rollback()

    with factory() as db:
        assert len(_imports(db)) == 2
        assert len(_snapshot_rows(db)) == 1
        assert not _imports(db, ROLLED_BACK_SOURCE)
        active, tables, events = _active_and_history(db)
        assert active.revision_id == ready.id
        assert active.schema_fingerprint == READY_FP
        assert tables == ["T1"]
        assert len(events) == 1
        assert events[0].activated_revision_id == ready.id
