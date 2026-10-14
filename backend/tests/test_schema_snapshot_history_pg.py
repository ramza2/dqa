"""PostgreSQL-only S-04-B acceptance tests against disposable isolated database.

Run only with DQA_PR73_ISOLATED_PG=1 and database name prefix
'dqa_snapshot_pr73_'. Never use DQA main/dev DB. Migration is executed by
the external, explicitly isolated test runner before these tests.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.adapters.schema_inspector.base import (
    InspectedColumn, InspectedTable, SchemaSnapshot,
)
from app.core.config import get_settings
from app.models.schema_snapshot_revision import SchemaSnapshotRevision
from app.services.schema_snapshot_history import (
    SnapshotHistoryError, capture_snapshot_revision, get_snapshot_revision,
    list_snapshot_revisions,
)

pytestmark = pytest.mark.integration

if os.environ.get("DQA_PR73_ISOLATED_PG") != "1":
    pytest.skip("requires an expressly isolated disposable PostgreSQL database", allow_module_level=True)


@pytest.fixture(scope="module")
def factory():
    settings = get_settings()
    if (
        not settings.dqa_db_name.startswith("dqa_snapshot_pr73_")
        or settings.dqa_db_host != "127.0.0.1"
        or settings.dqa_db_port <= 1024
    ):
        pytest.fail("refusing to run Snapshot history PG tests outside disposable loopback DB")
    engine = create_engine(
        settings.sqlalchemy_database_url,
        pool_pre_ping=True, future=True,
        connect_args={"options": "-c statement_timeout=10000"},
    )
    try:
        with engine.connect() as conn:
            assert conn.scalar(text("select current_database()")) == settings.dqa_db_name
            assert conn.scalar(text("select to_regclass('public.schema_snapshot_revisions')"))
        yield sessionmaker(bind=engine, expire_on_commit=False, future=True)
    finally:
        engine.dispose()


def _snapshot():
    return SchemaSnapshot(
        db_type="oracle", database_name="FREEPDB1", schema_name="DEMIS_OWNER",
        tables=[InspectedTable("DEMIS_OWNER", "TB_FAKE", "BASE TABLE", "합성 테이블")],
        columns=[
            InspectedColumn(
                "DEMIS_OWNER", "TB_FAKE", 1, "ID", "NUMBER",
                None, 12, 0, False, None, "합성 컬럼",
            )
        ],
    )


def _append(session, source, *, expected=None, request_id=None, snapshot=None):
    return capture_snapshot_revision(
        session, snapshot or _snapshot(),
        source_name=source, captured_by="synthetic-operator",
        capture_request_id=request_id or uuid4(),
        expected_previous_revision_id=expected,
    )


def test_pg_migrated_append_revision_idempotency_cas_and_integrity(factory):
    source = "mock_pg_" + uuid4().hex[:10]
    req = uuid4()
    with factory() as db:
        first = _append(db, source, request_id=req).revision
        first_id = first.id
        db.commit()

    with factory() as db:
        replay = _append(db, source, request_id=req)
        assert not replay.created and replay.revision.id == first_id
        db.commit()

    with factory() as db:
        with pytest.raises(SnapshotHistoryError, match="STALE_SNAPSHOT_REVISION"):
            _append(db, source, expected=None)
        db.rollback()

    changed = deepcopy(_snapshot())
    changed.columns[0] = replace(changed.columns[0], column_comment="변경된 주석")
    with factory() as db:
        second = _append(db, source, expected=first_id, snapshot=changed).revision
        second_id = second.id
        assert second.diff_summary_json["total_changes"] == 1
        assert second.diff_summary_json["changes"][0]["changed_fields"] == ["column_comment"]
        db.commit()

    with factory() as db:
        rows = list_snapshot_revisions(db, source_name=source)
        assert [r.id for r in rows] == [second_id, first_id]
        assert get_snapshot_revision(db, second_id, source_name=source) is not None
        assert get_snapshot_revision(db, second_id, source_name=source + "_other") is None
        assert rows[0].diff_summary_json["base_revision_id"] == first_id
        original = get_snapshot_revision(db, first_id, source_name=source)
        assert original.diff_summary_json["status"] == "NO_BASELINE"
        row = SchemaSnapshotRevision(**{
            col.key: getattr(original, col.key)
            for col in SchemaSnapshotRevision.__table__.columns
            if col.key not in ("id", "captured_at")
        })
        db.add(row)
        with pytest.raises(IntegrityError):
            db.flush()  # real PostgreSQL unique(source_name, capture_request_id)
        db.rollback()


def test_pg_rollback_leaves_no_snapshot(factory):
    source = "mock_pg_" + uuid4().hex[:10]
    with factory() as db:
        pending = _append(db, source)
        assert pending.revision.id is not None
        db.rollback()
    with factory() as db:
        assert list_snapshot_revisions(db, source_name=source) == []


def test_pg_two_concurrent_first_captures_one_wins_one_stale(factory):
    source = "mock_pg_" + uuid4().hex[:10]
    barrier = Barrier(2)

    def capture():
        with factory() as db:
            barrier.wait(timeout=10)
            try:
                row = _append(db, source)
                db.commit()
                return ("COMMITTED", row.revision.id)
            except SnapshotHistoryError as exc:
                db.rollback()
                return (exc.code, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(capture)
        b = pool.submit(capture)
        results = [a.result(timeout=25), b.result(timeout=25)]
    assert sorted(result[0] for result in results) == [
        "COMMITTED", "STALE_SNAPSHOT_REVISION",
    ]
    with factory() as db:
        rows = list_snapshot_revisions(db, source_name=source)
        assert len(rows) == 1
        assert rows[0].previous_revision_id is None


def test_pg_history_http_source_scope_auth_and_no_raw_metadata(factory, monkeypatch):
    source = "mock_pg_" + uuid4().hex[:10]
    with factory() as db:
        rev = _append(db, source).revision
        rid = rev.id
        db.commit()

    from app.adapters.db.session import get_engine, get_session_factory
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    try:
        app = create_app(check_migrations_on_startup=True)
        with TestClient(app) as http:
            params = {"source_name": source}
            assert http.get("/api/v1/schema-inspector/snapshots", params=params).status_code == 401

            headers = {
                "X-DQA-Dev-Actor": "synthetic-reader",
                "X-DQA-Dev-Roles": "viewer",
            }
            res = http.get(
                "/api/v1/schema-inspector/snapshots", params=params, headers=headers
            )
            assert res.status_code == 200, res.status_code
            assert [x["id"] for x in res.json()] == [rid]
            assert "snapshot_json" not in res.text
            assert "capture_request_id" not in res.text

            detail = http.get(
                f"/api/v1/schema-inspector/snapshots/{rid}",
                params=params, headers=headers,
            )
            assert detail.status_code == 200
            assert detail.json()["diff_status"] == "NO_BASELINE"
            assert "snapshot_json" not in detail.text

            other = http.get(
                f"/api/v1/schema-inspector/snapshots/{rid}",
                params={"source_name": source + "_other"}, headers=headers,
            )
            assert other.status_code == 404
            assert http.post(
                "/api/v1/schema-inspector/snapshots", json={}, headers=headers,
            ).status_code == 405
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def test_pg_capture_http_commits_idempotent_replay_and_diff(factory, monkeypatch):
    """S-04-C-1 API→configured synthetic collector→real PostgreSQL→GET."""
    from app.adapters.db.session import get_engine, get_session_factory
    from app.main import create_app
    from app.services import schema_snapshot_capture as capture_service
    from app.services.schema_inspection import CollectedSchemaSnapshot

    source = "mock_pg_" + uuid4().hex[:10]
    state = {"snapshot": _snapshot(), "calls": 0}

    def synthetic_inspection(_settings):
        state["calls"] += 1
        return CollectedSchemaSnapshot(source_name=source, snapshot=state["snapshot"])

    monkeypatch.setattr(
        capture_service, "collect_configured_schema_snapshot", synthetic_inspection
    )
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    auth = {
        "X-DQA-Dev-Actor": "pg-capture-test-admin",
        "X-DQA-Dev-Roles": "administrator",
    }
    read_auth = {
        "X-DQA-Dev-Actor": "pg-capture-test-viewer",
        "X-DQA-Dev-Roles": "viewer",
    }
    first_idempotency_key = str(uuid4())
    try:
        app = create_app(check_migrations_on_startup=True)
        with TestClient(app) as http:
            url = "/api/v1/schema-inspector/snapshots/capture"
            base = {
                "capture_request_id": first_idempotency_key,
                "expected_previous_revision_id": None,
            }

            unauthorized = http.post(url, json=base, headers=read_auth)
            assert unauthorized.status_code == 403
            assert state["calls"] == 0

            first = http.post(url, json=base, headers=auth)
            assert first.status_code == 200, first.status_code
            first_data = first.json()
            assert first_data["created"] is True
            assert first_data["diff_status"] == "NO_BASELINE"
            assert first_data["imported"] is False
            assert first_data["activated"] is False
            first_id = first_data["id"]

            # Real commit: a separate session can see the row immediately.
            with factory() as db:
                assert get_snapshot_revision(
                    db, first_id, source_name=source
                ) is not None

            replay = http.post(url, json=base, headers=auth)
            assert replay.status_code == 200
            assert replay.json()["created"] is False
            assert replay.json()["id"] == first_id

            stale = http.post(
                url, json={
                    "capture_request_id": str(uuid4()),
                    "expected_previous_revision_id": None,
                }, headers=auth,
            )
            assert stale.status_code == 409
            assert stale.json()["detail"]["code"] == "STALE_SNAPSHOT_REVISION"

            updated = deepcopy(state["snapshot"])
            updated.columns[0] = replace(
                updated.columns[0], column_comment="synthetic update",
            )
            state["snapshot"] = updated
            second = http.post(
                url, json={
                    "capture_request_id": str(uuid4()),
                    "expected_previous_revision_id": first_id,
                }, headers=auth,
            )
            assert second.status_code == 200
            second_data = second.json()
            assert second_data["created"] is True
            assert second_data["previous_revision_id"] == first_id
            assert second_data["total_changes"] == 1

            listing = http.get(
                "/api/v1/schema-inspector/snapshots",
                params={"source_name": source}, headers=read_auth,
            )
            assert listing.status_code == 200
            assert [x["id"] for x in listing.json()] == [
                second_data["id"], first_id,
            ]
            detail = http.get(
                f"/api/v1/schema-inspector/snapshots/{second_data['id']}",
                params={"source_name": source}, headers=read_auth,
            )
            assert detail.status_code == 200
            assert detail.json()["changes"][0]["changed_fields"] == ["column_comment"]
            assert "synthetic update" not in detail.text
            assert "snapshot_json" not in detail.text
            assert "capture_request_id" not in detail.text
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def test_pg_change_review_event_http_cas_idempotency_and_catalog_isolation(
    factory, monkeypatch,
):
    """S-04-C-2B-1: real PostgreSQL journal and protected HTTP endpoints."""
    from app.adapters.db.session import get_engine, get_session_factory
    from app.main import create_app
    from app.models.schema_snapshot_review_event import SchemaSnapshotReviewEvent

    source = "review_pg_" + uuid4().hex[:10]
    with factory() as db:
        snap = _append(db, source).revision
        rid, fp = snap.id, snap.schema_fingerprint
        db.commit()

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DQA_AUTH_PROVIDER", "dev_headers")
    monkeypatch.setenv("DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED", "true")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    admin = {
        "X-DQA-Dev-Actor": "review-pg-admin",
        "X-DQA-Dev-Roles": "administrator",
    }
    viewer = {
        "X-DQA-Dev-Actor": "review-pg-viewer",
        "X-DQA-Dev-Roles": "viewer",
    }
    params = {"source_name": source}
    path = f"/api/v1/schema-inspector/snapshots/{rid}/reviews"
    req_uuid = str(uuid4())
    body = {
        "review_request_id": req_uuid,
        "expected_schema_fingerprint": fp,
        "expected_previous_review_event_id": None,
        "decision": "ACKNOWLEDGED",
        "reason_code": "REVIEWED_CHANGES",
    }
    try:
        with TestClient(create_app(check_migrations_on_startup=True)) as http:
            assert http.post(path, params=params, json=body).status_code == 401
            assert http.post(
                path, params=params, json=body, headers=viewer,
            ).status_code == 403

            first = http.post(path, params=params, json=body, headers=admin)
            assert first.status_code == 200, first.text
            row = first.json()
            assert row["created"] is True
            assert row["reviewed_by"] == "review-pg-admin"
            assert row["independent_preflight_verified"] is False
            assert row["catalog_ready"] is False
            assert row["catalog_activated"] is False
            event_id = row["id"]
            with factory() as db:
                assert db.get(SchemaSnapshotReviewEvent, event_id) is not None

            replay = http.post(path, params=params, json=body, headers=admin)
            assert replay.status_code == 200, replay.text
            assert replay.json()["created"] is False
            assert replay.json()["id"] == event_id

            conflict = http.post(
                path, params=params,
                json={**body, "decision": "CHANGES_REQUESTED",
                      "reason_code": "RECHECK_REQUIRED"},
                headers=admin,
            )
            assert conflict.status_code == 409
            assert conflict.json()["detail"]["code"] == "REVIEW_REQUEST_REUSED"

            stale = http.post(
                path, params=params,
                json={**body, "review_request_id": str(uuid4())},
                headers=admin,
            )
            assert stale.status_code == 409
            assert stale.json()["detail"]["code"] == "STALE_REVIEW_EVENT"

            second = http.post(
                path, params=params,
                json={
                    **body,
                    "review_request_id": str(uuid4()),
                    "expected_previous_review_event_id": event_id,
                    "decision": "CHANGES_REQUESTED",
                    "reason_code": "SCOPE_UNCLEAR",
                },
                headers=admin,
            )
            assert second.status_code == 200, second.text
            assert second.json()["previous_review_event_id"] == event_id

            history = http.get(path, params=params, headers=viewer)
            assert history.status_code == 200, history.text
            assert [x["id"] for x in history.json()] == [
                second.json()["id"], event_id,
            ]
            assert "review_request_id" not in history.text

            assert http.get(
                path, params={"source_name": "another_source"},
                headers=viewer,
            ).status_code == 404

            with factory() as db:
                later = _append(db, source, expected=rid).revision
                assert later.id != rid
                db.commit()

            old_review = http.post(
                path, params=params,
                json={
                    **body,
                    "review_request_id": str(uuid4()),
                    "expected_previous_review_event_id": second.json()["id"],
                },
                headers=admin,
            )
            assert old_review.status_code == 409, old_review.text
            assert old_review.json()["detail"]["code"] == "STALE_SNAPSHOT_REVISION"

            # Exactly two immutable events; no Catalog import / pointer changes.
            with factory() as db:
                count = db.scalar(
                    select(SchemaSnapshotReviewEvent)
                    .where(SchemaSnapshotReviewEvent.source_name == source)
                    .order_by(SchemaSnapshotReviewEvent.id.desc()).limit(1)
                )
                assert count.id == second.json()["id"]
                assert db.scalar(text(
                    "select count(*) from catalog_active_revisions"
                )) == 0
                assert db.scalar(text(
                    "select count(*) from catalog_import_revisions"
                )) == 0
    finally:
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
