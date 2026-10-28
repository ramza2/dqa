"""M3-A model-free template listing; synthetic disposable database only."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.query_template import QueryTemplateVersion
from tests.test_execution_form import (
    SOURCE, _approve_enable, _import_and_activate, _setup_form, _template_body
)

pytestmark = pytest.mark.integration
PATH = "/api/v1/query-executions/manual-templates"


def _create(db_client: TestClient, *, stable_key: str, approved: bool = True):
    res = db_client.post(
        "/api/v1/query-templates",
        json=_template_body(stable_key=stable_key, name=stable_key),
    )
    assert res.status_code == 201, res.text
    return (
        _approve_enable(db_client, res.json()["id"])
        if approved else res.json()
    )


def test_manual_template_catalog_gates_and_never_calls_llm_or_demis(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    one = _setup_form(db_session, db_client, fingerprint="fp-m3a")
    second = _create(db_client, stable_key="m3a.second")
    _create(db_client, stable_key="m3a.unapproved", approved=False)
    monkeypatch.setattr(
        "app.services.template_recommendation.create_llm_provider",
        MagicMock(side_effect=AssertionError("must not call model")),
    )
    monkeypatch.setattr(
        "app.adapters.demis.factory.create_readonly_demis_adapter",
        MagicMock(side_effect=AssertionError("must not connect to DEMIS")),
    )

    res = db_client.get(PATH, params={"source_name": SOURCE["source_name"]})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2
    assert {x["template_id"] for x in body["items"]} == {
        one["template_id"], second["id"]
    }
    assert body["catalog_revision_id"] == one["revision"].id
    assert body["schema_fingerprint"] == "fp-m3a"
    assert res.headers["cache-control"] == "no-store, private"
    assert res.headers["pragma"] == "no-cache"
    for forbidden in ("sql_text", "SELECT ward_cd", "credential_secret_ref",
                      "host", "password", "row_limit", "PATIENT-SECRET"):
        assert forbidden not in res.text

    page = db_client.get(PATH, params={
        "source_name": SOURCE["source_name"], "limit": 1, "offset": 1
    })
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert len(page.json()["items"]) == 1
    assert page.json()["items"][0] == body["items"][1]


def test_manual_catalog_excludes_stale_unsafe_and_oversize(
    db_session: Session, db_client: TestClient
):
    one = _setup_form(db_session, db_client, fingerprint="fp-m3a-filter")
    unsafe = _create(db_client, stable_key="m3a.unsafe")
    oversized = _create(db_client, stable_key="m3a.large")
    from app.adapters.demis.types import MAX_SQL_TEXT_LENGTH
    db_session.get(QueryTemplateVersion, unsafe["version"]["id"]).sql_text = (
        "DELETE FROM dual"
    )
    db_session.get(QueryTemplateVersion, oversized["version"]["id"]).sql_text = (
        "SELECT 1 FROM dual -- " + "x" * (MAX_SQL_TEXT_LENGTH + 1)
    )
    db_session.commit()
    res = db_client.get(PATH, params={"source_name": SOURCE["source_name"]})
    assert res.status_code == 200
    assert [i["template_id"] for i in res.json()["items"]] == [one["template_id"]]

    _import_and_activate(db_session, fingerprint="fp-m3a-new-active")
    db_session.commit()
    stale = db_client.get(PATH, params={"source_name": SOURCE["source_name"]})
    assert stale.status_code == 200
    assert stale.json()["items"] == []
    assert stale.json()["total"] == 0


@pytest.mark.parametrize("role,expected", [
    ("query_operator", 200),
    ("administrator", 200),
    ("viewer", 403),
    ("auditor", 403),
    ("template_author", 403),
])
def test_manual_catalog_rbac(
    db_session: Session, db_client: TestClient,
    unauth_db_client: TestClient, role: str, expected: int
):
    _setup_form(
        db_session, db_client, fingerprint=f"fp-m3a-role-{role}",
        template_overrides={"stable_key": f"m3a.role.{role}"}
    )
    res = unauth_db_client.get(
        PATH, params={"source_name": SOURCE["source_name"]},
        headers={"X-DQA-Dev-Actor": "tester", "X-DQA-Dev-Roles": role},
    )
    assert res.status_code == expected


def test_manual_catalog_missing_source_and_unauthenticated(unauth_db_client):
    assert unauth_db_client.get(PATH, params={"source_name": "x"}).status_code == 401


def test_manual_catalog_validation_and_missing_active(db_client):
    assert db_client.get(PATH, params={"source_name": "x", "limit": 101}).status_code == 422
    assert db_client.get(PATH, params={"source_name": "x", "offset": -1}).status_code == 422
    assert db_client.get(PATH, params={"source_name": "absent"}).status_code == 404
