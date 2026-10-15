"""S-03-D real transaction acceptance ONLY against disposable loopback PG.

Does not import db_session/db_client, run TRUNCATE, touch Oracle/DEMIS,
inspect patient data or modify an existing DQA service database.
Use scripts/dqa-s03d-disposable-pg-check.sh to create tmpfs DB first.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
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
from app.services import catalog_active
from app.services.catalog_active import (
    activate_catalog_revision, get_active_catalog,
)
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.catalog_query import list_tables
from app.services.schema_catalog_candidate import build_catalog_v2_candidate
from app.services.schema_snapshot_history import capture_snapshot_revision
from app.services.schema_snapshot_review import build_latest_snapshot_warning_candidate
from tests.catalog_package_fixtures import DEFAULT_SOURCE, build_package_zip
from tests.test_schema_snapshot_history import _base

pytestmark = pytest.mark.integration

if os.environ.get("DQA_S03D_ISOLATED_PG") != "1":
    pytest.skip("S-03-D requires dedicated disposable PostgreSQL", allow_module_level=True)


@pytest.fixture(scope="module")
def factory():
    cfg = get_settings()
    if (
        cfg.app_env != "test"
        or cfg.dqa_db_host != "127.0.0.1"
        or cfg.dqa_db_port != 55439
        or cfg.dqa_db_name != "dqa_s03d_disposable"
        or cfg.dqa_db_user != "dqa_s03d_user"
    ):
        pytest.fail("refusing S-03-D test outside explicit disposable loopback DB")
    engine = create_engine(
        cfg.sqlalchemy_database_url,
        pool_pre_ping=True, future=True,
        connect_args={
            "connect_timeout": 3,
            "options": "-c statement_timeout=10000",
        },
    )
    try:
        with engine.connect() as db:
            assert db.scalar(text("SELECT current_database()")) == "dqa_s03d_disposable"
            assert db.scalar(text("SELECT current_user")) == "dqa_s03d_user"
            for table in (
                "catalog_import_revisions",
                "catalog_active_revisions",
                "catalog_activation_events",
                "schema_snapshot_revisions",
            ):
                assert db.scalar(text(
                    "SELECT to_regclass(:table)"
                ), {"table": f"public.{table}"}) is not None
        yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    finally:
        engine.dispose()


def _source():
    return "s03d_pg_" + uuid4().hex[:16]


def _ready(factory, source, fingerprint):
    definition = {**DEFAULT_SOURCE, "source_name": source}
    archive = build_package_zip(
        package_readiness="READY",
        source=definition,
        fingerprint=fingerprint,
    )
    with factory() as db:
        row, created = import_catalog_package_bytes(archive, db)
        assert created is True
        result_id = row.id
        db.commit()
    return result_id


def _capture(factory, source):
    with factory() as db:
        revision = capture_snapshot_revision(
            db, _base(),
            source_name=source,
            captured_by="s03d-synthetic-operator",
            capture_request_id=uuid4(),
            expected_previous_revision_id=None,
        ).revision
        revision_id = revision.id
        db.commit()
    with factory() as db:
        candidate = build_latest_snapshot_warning_candidate(
            db, source_name=source, revision_id=revision_id,
        )
    return revision_id, candidate


def _state(factory, source):
    with factory() as db:
        active = get_active_catalog(db, source)
        table_names = [t.name for t in list_tables(db, source)[1].items]
        event_count = int(db.scalar(
            select(func.count()).select_from(CatalogActivationEvent).where(
                CatalogActivationEvent.source_name == source,
            )
        ) or 0)
        return (active.revision_id, active.schema_fingerprint, table_names, event_count)


def _assert_ready_active(factory, source, ready_id, expected_state):
    actual = _state(factory, source)
    assert actual == expected_state
    assert actual[0] == ready_id


def test_real_pg_warning_import_and_duplicate_never_change_active_ready(factory):
    source = _source()
    ready_id = _ready(factory, source, "synthetic-ready-" + source)
    with factory() as db:
        activated = activate_catalog_revision(db, ready_id)
        assert activated.changed
        db.commit()
    baseline = _state(factory, source)
    assert baseline[2]

    revision_id, candidate = _capture(factory, source)
    assert candidate.revision_id == revision_id
    assert candidate.package_readiness == "WARNING"
    assert candidate.preflight_status == "NOT_VERIFIED"
    assert candidate.activation_eligible is False

    with factory() as db:
        warning, created = import_catalog_package_bytes(candidate.archive_bytes, db)
        assert created
        warning_id = warning.id
        assert warning.package_readiness == "WARNING"
        db.commit()
    _assert_ready_active(factory, source, ready_id, baseline)

    with factory() as db:
        duplicate, created = import_catalog_package_bytes(candidate.archive_bytes, db)
        assert created is False
        assert duplicate.id == warning_id
        db.commit()

    with factory() as db:
        with pytest.raises(CatalogActivationError) as caught:
            activate_catalog_revision(db, warning_id)
        assert caught.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
        db.rollback()
    _assert_ready_active(factory, source, ready_id, baseline)

    with factory() as db:
        rows = db.scalars(
            select(CatalogImportRevision).where(
                CatalogImportRevision.source_name == source
            )
        ).all()
        assert len(rows) == 2
        assert {r.package_readiness for r in rows} == {"READY", "WARNING"}
        assert db.get(SchemaSnapshotRevision, revision_id) is not None


def test_real_pg_staged_import_rollback_preserves_active_and_history(factory):
    source = _source()
    ready_id = _ready(factory, source, "ready-" + source)
    with factory() as db:
        activate_catalog_revision(db, ready_id)
        db.commit()
    baseline = _state(factory, source)
    warning = build_catalog_v2_candidate(
        _base(),
        source_name=source,
        generated_at=datetime(2026, 10, 15, tzinfo=timezone.utc),
    )

    with factory() as db:
        staged, created = import_catalog_package_bytes(warning, db)
        assert created and staged.id is not None
        uncommitted_id = staged.id
        db.rollback()  # explicit injected failure before commit

    with factory() as db:
        assert db.get(CatalogImportRevision, uncommitted_id) is None
        assert db.scalars(select(CatalogImportRevision).where(
            CatalogImportRevision.source_name == source
        )).all().__len__() == 1
    _assert_ready_active(factory, source, ready_id, baseline)

    with factory() as db:
        persisted, created = import_catalog_package_bytes(warning, db)
        assert created and persisted.package_readiness == "WARNING"
        db.commit()
    _assert_ready_active(factory, source, ready_id, baseline)


def test_real_pg_activation_event_failure_rolls_back_pointer_update(
    factory, monkeypatch,
):
    source = _source()
    ready_a = _ready(factory, source, "ready-a-" + source)
    ready_b = _ready(factory, source, "ready-b-" + source)
    with factory() as db:
        activate_catalog_revision(db, ready_a)
        db.commit()
    baseline = _state(factory, source)
    assert baseline[3] == 1

    def injected_failure(_self, _event):
        raise RuntimeError("injected synthetic activation event failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            catalog_active.CatalogActiveRepository, "add_event", injected_failure
        )
        with factory() as db:
            # The real service has already issued UPDATE + flush on the active
            # pointer when event persistence fails; rollback must undo UPDATE.
            with pytest.raises(RuntimeError, match="injected synthetic"):
                activate_catalog_revision(db, ready_b)
            db.rollback()

    _assert_ready_active(factory, source, ready_a, baseline)
    with factory() as db:
        pointer = db.scalar(select(CatalogActiveRevision).where(
            CatalogActiveRevision.source_name == source
        ))
        assert pointer is not None and pointer.catalog_import_revision_id == ready_a
        assert db.scalar(select(func.count()).select_from(
            CatalogActivationEvent
        ).where(CatalogActivationEvent.source_name == source)) == 1


def test_real_pg_explicit_switch_to_previous_ready_not_warning(factory):
    source = _source()
    ready_a = _ready(factory, source, "restore-a-" + source)
    ready_b = _ready(factory, source, "restore-b-" + source)
    with factory() as db:
        activate_catalog_revision(db, ready_a)
        db.commit()
    with factory() as db:
        activate_catalog_revision(db, ready_b)
        db.commit()

    _, warning_zip = _capture(factory, source)
    with factory() as db:
        warn, created = import_catalog_package_bytes(warning_zip.archive_bytes, db)
        assert created
        warning_id = warn.id
        db.commit()
    with factory() as db:
        with pytest.raises(CatalogActivationError) as caught:
            activate_catalog_revision(db, warning_id)
        assert caught.value.code == CatalogActivationErrorCode.REVISION_NOT_ACTIVATABLE
        db.rollback()
    assert _state(factory, source)[0] == ready_b

    with factory() as db:
        result = activate_catalog_revision(db, ready_a)
        assert result.changed and result.previous_revision_id == ready_b
        db.commit()
    state = _state(factory, source)
    assert state[0] == ready_a
    assert state[3] == 3  # READY A, READY B, explicit READY A
    with factory() as db:
        warning = db.get(CatalogImportRevision, warning_id)
        assert warning.package_readiness == "WARNING"
        assert int(db.scalar(
            select(func.count()).select_from(SchemaSnapshotRevision).where(
                SchemaSnapshotRevision.source_name == source
            )
        ) or 0) == 1
