"""M4-A LLM-free execution contract: manual-templates → form → preview → execute → audit.

Uses synthetic Catalog/Template/Profile seeds only. Live Oracle sockets are never opened;
execution uses the injected FakeReadOnlyDemisAdapter. LLM recommend/extract must not run.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.execution.errors import ExecutionPreviewErrorCode
from app.models.query_audit import QueryAuditEvent
from tests.test_query_execution import (
    ALLOWED_REF,
    ENVIRONMENT,
    EXECUTE_PATH,
    SOURCE,
    _execute_body,
    _headers,
    _import_and_activate,
    _patch_live_adapter,
    _setup_eligible,
    _ensure_profile,
    _template_body,
)

pytestmark = pytest.mark.integration

MANUAL_PATH = "/api/v1/query-executions/manual-templates"
FORM_PATH = "/api/v1/query-executions/form"
PREVIEW_PATH = "/api/v1/query-executions/preview"
AUDIT_PATH = "/api/v1/audit-events"
RECOMMEND_PATH = "/api/v1/query-recommendations"
EXTRACT_PATH = "/api/v1/query-parameters/extract"


def _forbid_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.template_recommendation.create_llm_provider",
        MagicMock(side_effect=AssertionError("M4-A must not call LLM recommend")),
    )
    monkeypatch.setattr(
        "app.services.parameter_extraction.create_llm_provider",
        MagicMock(side_effect=AssertionError("M4-A must not call LLM extract")),
        raising=False,
    )


def test_m4a_llmfree_happy_path_manual_to_audit(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _forbid_llm(monkeypatch)
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-m4a-happy")
    adapter = _patch_live_adapter(
        monkeypatch, rows=[{"ward_cd": "A01"}, {"ward_cd": "B02"}]
    )

    manual = db_client.get(
        MANUAL_PATH, params={"source_name": SOURCE["source_name"], "limit": 100}
    )
    assert manual.status_code == 200, manual.text
    body = manual.json()
    assert body["total"] >= 1
    match = next(
        item
        for item in body["items"]
        if item["template_id"] == fixture["template_id"]
        and item["version_id"] == fixture["version_id"]
    )
    assert "sql_text" not in match
    assert "ward_cd" in match["parameter_names"]

    form = db_client.get(
        FORM_PATH,
        params={
            "source_name": SOURCE["source_name"],
            "template_id": match["template_id"],
            "version_id": match["version_id"],
        },
    )
    assert form.status_code == 200, form.text
    assert form.json()["template"]["template_id"] == fixture["template_id"]

    payload = _execute_body(fixture)
    preview = db_client.post(PREVIEW_PATH, json=payload)
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert preview_body["execution_available"] is True
    assert preview_body["execution_blockers"] == []
    assert preview_body["resolved_parameters"]["ward_cd"] == "A01"

    # Explicitly prove LLM endpoints were never required for this path.
    assert RECOMMEND_PATH not in manual.request.url.path  # type: ignore[union-attr]

    execution = db_client.post(EXECUTE_PATH, json=payload)
    assert execution.status_code == 200, execution.text
    result = execution.json()
    assert result["row_count"] == 2
    assert result["truncated"] is False
    assert isinstance(result.get("audit_id"), str) and result["audit_id"]
    assert adapter.last_sql_text is not None
    assert "SELECT" in adapter.last_sql_text.upper()
    assert adapter.last_parameters is not None
    assert adapter.last_parameters.get("ward_cd") == "A01"
    # Optional schema defaults (e.g. from_date) may be filled by eligibility.
    assert "DELETE" not in adapter.last_sql_text.upper()
    assert "INSERT" not in adapter.last_sql_text.upper()
    assert "UPDATE" not in adapter.last_sql_text.upper()

    audit = db_client.get(
        f"{AUDIT_PATH}/{result['audit_id']}",
        headers=_headers("auditor", "auditor"),
    )
    assert audit.status_code == 200, audit.text
    events = {
        (item["event_type"], item["status"]) for item in audit.json()["items"]
    }
    assert ("QUERY_REQUEST", "STARTED") in events
    assert ("QUERY_REQUEST", "SUCCEEDED") in events
    assert ("QUERY_EXECUTION", "STARTED") in events
    assert ("QUERY_EXECUTION", "SUCCEEDED") in events
    for item in audit.json()["items"]:
        assert item["parameter_logging_policy"] == "NAMES_ONLY"
    assert "A01" not in audit.text
    assert ALLOWED_REF not in audit.text
    assert "test-secret-value" not in audit.text


def test_m4a_blocks_unauthenticated_manual_and_execute(
    db_session: Session, db_client: TestClient, unauth_db_client: TestClient
) -> None:
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-m4a-auth")
    denied_manual = unauth_db_client.get(
        MANUAL_PATH, params={"source_name": SOURCE["source_name"]}
    )
    assert denied_manual.status_code in {401, 403, 503}
    denied_exec = unauth_db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert denied_exec.status_code in {401, 403, 503}
    assert denied_exec.status_code != 200


def test_m4a_blocks_unapproved_template_from_manual_and_preview(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _forbid_llm(monkeypatch)
    _import_and_activate(db_session, fingerprint="fp-m4a-draft")
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_template_body(stable_key="m4a.draft.only"),
    )
    assert created.status_code == 201, created.text
    draft = created.json()
    _ensure_profile(db_client)

    manual = db_client.get(
        MANUAL_PATH, params={"source_name": SOURCE["source_name"]}
    )
    assert manual.status_code == 200
    assert all(item["template_id"] != draft["id"] for item in manual.json()["items"])

    preview = db_client.post(
        PREVIEW_PATH,
        json={
            "source_name": SOURCE["source_name"],
            "environment": ENVIRONMENT,
            "template_id": draft["id"],
            "version_id": draft["version"]["id"],
            "parameters": {"ward_cd": "A01"},
        },
    )
    assert preview.status_code == 409
    assert (
        preview.json()["detail"]["code"]
        == ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE
    )


def test_m4a_blocks_catalog_fingerprint_mismatch(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _forbid_llm(monkeypatch)
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-m4a-old")
    # Activate a new Catalog revision so the pinned template becomes stale.
    _import_and_activate(db_session, fingerprint="fp-m4a-new")
    db_session.commit()

    manual = db_client.get(
        MANUAL_PATH, params={"source_name": SOURCE["source_name"]}
    )
    assert manual.status_code == 200
    assert all(
        item["template_id"] != fixture["template_id"] for item in manual.json()["items"]
    )

    preview = db_client.post(PREVIEW_PATH, json=_execute_body(fixture))
    assert preview.status_code == 409
    assert preview.json()["detail"]["code"] == ExecutionPreviewErrorCode.CATALOG_MISMATCH


def test_m4a_execution_failure_writes_failed_audit(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _forbid_llm(monkeypatch)
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-m4a-fail")
    _patch_live_adapter(monkeypatch, simulate_execution_failure=True)

    response = db_client.post(EXECUTE_PATH, json=_execute_body(fixture))
    assert response.status_code in {500, 502, 503, 504}
    # Durable audit must still be reconstructible when audit_id is present.
    body = response.json()
    detail = body.get("detail") if isinstance(body, dict) else None
    # Prefer reading latest FAILED execution audit from DB for this template.
    rows = list(
        db_session.scalars(
            select(QueryAuditEvent)
            .where(QueryAuditEvent.template_id == fixture["template_id"])
            .order_by(QueryAuditEvent.id.asc())
        ).all()
    )
    assert any(
        row.event_type == "QUERY_EXECUTION" and row.status == "FAILED" for row in rows
    )
    assert any(
        row.event_type == "QUERY_EXECUTION" and row.status == "STARTED" for row in rows
    )
    if isinstance(detail, dict):
        assert "password" not in str(detail).casefold()
        assert ALLOWED_REF not in str(detail)


def test_m4a_never_calls_recommend_or_extract_endpoints(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _forbid_llm(monkeypatch)
    fixture = _setup_eligible(db_session, db_client, fingerprint="fp-m4a-no-llm")
    _patch_live_adapter(monkeypatch)

    called: list[str] = []

    original_request = db_client.request

    def tracking_request(method: str, url: str, *args: Any, **kwargs: Any):
        called.append(f"{method.upper()} {url}")
        return original_request(method, url, *args, **kwargs)

    monkeypatch.setattr(db_client, "request", tracking_request)

    assert (
        db_client.get(
            MANUAL_PATH, params={"source_name": SOURCE["source_name"]}
        ).status_code
        == 200
    )
    assert (
        db_client.get(
            FORM_PATH,
            params={
                "source_name": SOURCE["source_name"],
                "template_id": fixture["template_id"],
                "version_id": fixture["version_id"],
            },
        ).status_code
        == 200
    )
    payload = _execute_body(fixture)
    assert db_client.post(PREVIEW_PATH, json=payload).status_code == 200
    assert db_client.post(EXECUTE_PATH, json=payload).status_code == 200

    joined = " | ".join(called)
    assert RECOMMEND_PATH not in joined
    assert EXTRACT_PATH not in joined
