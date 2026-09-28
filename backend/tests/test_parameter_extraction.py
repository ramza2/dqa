"""Parameter Extraction integration tests (eligibility, egress, LLM stub)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adapters.llm.errors import LLMProviderError, LLMProviderErrorCode
from app.adapters.parameter_extraction.errors import (
    ParameterExtractionError,
    ParameterExtractionErrorCode,
)
from app.core.config import Settings
from app.schemas.llm import LLMRequestPurpose
from app.schemas.parameter_extraction import (
    ISSUE_MISSING_REQUIRED,
    ISSUE_TYPE_MISMATCH,
    PARAMETER_EXTRACTION_MAX_TOKENS,
    LLMExtractedParameter,
    LLMParameterExtraction,
    ParameterExtractionRequest,
)
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.parameter_extraction import extract_query_parameters
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)
from tests.fakes.llm import StubLLMProvider, make_structured_result

pytestmark = pytest.mark.integration

SOURCE_A = dict(DEFAULT_SOURCE)
SYNTHETIC = "SYNTHETIC-PATIENT-001"


def _settings(*, allow_raw: bool = True) -> Settings:
    return Settings(
        APP_ENV="test",
        DQA_DB_HOST="localhost",
        DQA_DB_PORT=5432,
        DQA_DB_NAME="dqa",
        DQA_DB_USER="dqa",
        DQA_DB_PASSWORD="change-me",
        LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST=allow_raw,
        LLM_BASE_URL="https://llm.example",
        LLM_MODEL="demo-model",
    )


def _import_and_activate(session: Session, *, fingerprint: str):
    files = build_core_documents(
        source=SOURCE_A,
        fingerprint=fingerprint,
        tables=[{"schema": "DEMIS_OWNER", "name": "T1"}],
    )
    archive = build_package_zip(
        package_readiness="READY",
        source=SOURCE_A,
        fingerprint=fingerprint,
        files=files,
    )
    revision, created = import_catalog_package_bytes(archive, session)
    assert created is True
    activate_catalog_revision(session, revision.id)
    session.flush()
    return revision


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "stable_key": "ward.history",
        "name": "병동 이력",
        "description": "병동 이력 조회",
        "source_name": SOURCE_A["source_name"],
        "target_schemas": ["DEMIS_OWNER"],
        "sql_text": (
            "SELECT 1 FROM dual WHERE ward_cd = :ward_cd "
            "AND from_date = :from_date"
        ),
        "parameter_schema": [
            {
                "name": "ward_cd",
                "label": "병동 코드",
                "type": "string",
                "required": True,
                "pattern": r"^[A-Z][0-9]{2}$",
            },
            {
                "name": "from_date",
                "label": "시작일",
                "type": "date",
                "required": True,
            },
        ],
        "row_limit": 50,
        "timeout_seconds": 15,
    }
    body.update(overrides)
    return body


def _approve_enable(db_client: TestClient, template_id: int) -> dict[str, Any]:
    assert db_client.post(
        f"/api/v1/query-templates/{template_id}/submit-review", json={}
    ).status_code == 200
    assert db_client.post(
        f"/api/v1/query-templates/{template_id}/approve", json={}
    ).status_code == 200
    enabled = db_client.post(f"/api/v1/query-templates/{template_id}/enable")
    assert enabled.status_code == 200
    return enabled.json()


def _create_eligible(
    db_session: Session,
    db_client: TestClient,
    *,
    fingerprint: str = "fp-pex",
    **overrides: Any,
) -> dict[str, Any]:
    _import_and_activate(db_session, fingerprint=fingerprint)
    db_session.commit()
    created = db_client.post("/api/v1/query-templates", json=_create_body(**overrides))
    assert created.status_code == 201, created.text
    return _approve_enable(db_client, created.json()["id"])


def _extraction(
    *,
    values: list[dict[str, Any]] | None = None,
    unresolved: list[str] | None = None,
) -> LLMParameterExtraction:
    return LLMParameterExtraction(
        values=[LLMExtractedParameter(**item) for item in (values or [])],
        unresolved_parameter_names=list(unresolved or []),
    )


def _stub(extraction: LLMParameterExtraction) -> StubLLMProvider:
    return StubLLMProvider(result=make_structured_result(extraction))


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_eligible_template_extraction_success(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(db_session, db_client, stable_key="pex_ok")
    stub = _stub(
        _extraction(
            values=[
                {"name": "ward_cd", "value": "A01"},
                {"name": "from_date", "value": "2026-09-01"},
            ]
        )
    )
    result = extract_query_parameters(
        db_session,
        ParameterExtractionRequest(
            source_name=SOURCE_A["source_name"],
            template_id=detail["id"],
            version_id=detail["current_version_id"],
            request_text=f"{SYNTHETIC} A01 병동 2026-09-01 이력",
        ),
        llm_provider=stub,
        settings=_settings(allow_raw=True),
    )
    assert result.needs_clarification is False
    assert result.resolved_parameters == {
        "ward_cd": "A01",
        "from_date": "2026-09-01",
    }
    assert len(stub.calls) == 1
    assert stub.calls[0].purpose == LLMRequestPurpose.PARAMETER_EXTRACTION
    assert stub.calls[0].max_tokens == PARAMETER_EXTRACTION_MAX_TOKENS


def test_template_not_found(db_session: Session) -> None:
    _import_and_activate(db_session, fingerprint="fp-missing")
    db_session.commit()
    stub = _stub(_extraction())
    with pytest.raises(ParameterExtractionError) as exc_info:
        extract_query_parameters(
            db_session,
            ParameterExtractionRequest(
                source_name=SOURCE_A["source_name"],
                template_id=999999,
                version_id=1,
                request_text="x",
            ),
            llm_provider=stub,
            settings=_settings(allow_raw=True),
        )
    assert exc_info.value.code == ParameterExtractionErrorCode.TEMPLATE_NOT_FOUND
    assert stub.calls == []


def test_source_mismatch_and_stale_version(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(db_session, db_client, stable_key="pex_src")
    stub = _stub(_extraction())
    with pytest.raises(ParameterExtractionError) as exc_info:
        extract_query_parameters(
            db_session,
            ParameterExtractionRequest(
                source_name="other_source",
                template_id=detail["id"],
                version_id=detail["current_version_id"],
                request_text="x",
            ),
            llm_provider=stub,
            settings=_settings(allow_raw=True),
        )
    assert exc_info.value.code == ParameterExtractionErrorCode.TEMPLATE_NOT_ELIGIBLE
    assert stub.calls == []

    with pytest.raises(ParameterExtractionError) as exc_info:
        extract_query_parameters(
            db_session,
            ParameterExtractionRequest(
                source_name=SOURCE_A["source_name"],
                template_id=detail["id"],
                version_id=999999,
                request_text="x",
            ),
            llm_provider=stub,
            settings=_settings(allow_raw=True),
        )
    assert exc_info.value.code == ParameterExtractionErrorCode.STALE_VERSION
    assert stub.calls == []


@pytest.mark.parametrize(
    "status_setup",
    ["draft", "in_review", "rejected", "disabled", "incompatible", "unsafe"],
)
def test_ineligible_statuses_skip_llm(
    db_session: Session,
    db_client: TestClient,
    status_setup: str,
) -> None:
    stub = _stub(_extraction(values=[{"name": "ward_cd", "value": "A01"}]))
    if status_setup == "draft":
        _import_and_activate(db_session, fingerprint="fp-draft")
        db_session.commit()
        created = db_client.post(
            "/api/v1/query-templates",
            json=_create_body(stable_key="pex_draft"),
        ).json()
        template_id = created["id"]
        version_id = created["current_version_id"]
    elif status_setup == "in_review":
        _import_and_activate(db_session, fingerprint="fp-review")
        db_session.commit()
        created = db_client.post(
            "/api/v1/query-templates",
            json=_create_body(stable_key="pex_review"),
        ).json()
        template_id = created["id"]
        version_id = created["current_version_id"]
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review", json={}
        ).status_code == 200
    elif status_setup == "rejected":
        _import_and_activate(db_session, fingerprint="fp-rej")
        db_session.commit()
        created = db_client.post(
            "/api/v1/query-templates",
            json=_create_body(stable_key="pex_rej"),
        ).json()
        template_id = created["id"]
        version_id = created["current_version_id"]
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/reject",
            json={"note": "no"},
        ).status_code == 200
    elif status_setup == "disabled":
        detail = _create_eligible(
            db_session, db_client, fingerprint="fp-dis", stable_key="pex_dis"
        )
        template_id = detail["id"]
        version_id = detail["current_version_id"]
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/disable"
        ).status_code == 200
    elif status_setup == "incompatible":
        detail = _create_eligible(
            db_session, db_client, fingerprint="fp-old", stable_key="pex_old"
        )
        template_id = detail["id"]
        version_id = detail["current_version_id"]
        _import_and_activate(db_session, fingerprint="fp-new")
        db_session.commit()
    else:  # unsafe
        detail = _create_eligible(
            db_session,
            db_client,
            fingerprint="fp-unsafe",
            stable_key="pex_unsafe",
            sql_text="DELETE FROM T",
            parameter_schema=[],
            name="unsafe",
            description="unsafe",
        )
        # no-param unsafe still fails eligibility via SQL safety before no-param shortcut
        # Wait - empty params skip LLM but eligibility checks SQL safety first.
        template_id = detail["id"]
        version_id = detail["current_version_id"]

    with pytest.raises(ParameterExtractionError) as exc_info:
        extract_query_parameters(
            db_session,
            ParameterExtractionRequest(
                source_name=SOURCE_A["source_name"],
                template_id=template_id,
                version_id=version_id,
                request_text="x",
            ),
            llm_provider=stub,
            settings=_settings(allow_raw=True),
        )
    assert exc_info.value.code in {
        ParameterExtractionErrorCode.TEMPLATE_NOT_ELIGIBLE,
        ParameterExtractionErrorCode.STALE_VERSION,
    }
    assert stub.calls == []


# ---------------------------------------------------------------------------
# Egress / no-param / prompt privacy
# ---------------------------------------------------------------------------


def test_egress_gate_default_blocks_llm(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(db_session, db_client, stable_key="pex_egress")
    stub = _stub(_extraction(values=[{"name": "ward_cd", "value": "A01"}]))
    with pytest.raises(ParameterExtractionError) as exc_info:
        extract_query_parameters(
            db_session,
            ParameterExtractionRequest(
                source_name=SOURCE_A["source_name"],
                template_id=detail["id"],
                version_id=detail["current_version_id"],
                request_text=f"{SYNTHETIC} A01",
            ),
            llm_provider=stub,
            settings=_settings(allow_raw=False),
        )
    assert exc_info.value.code == ParameterExtractionErrorCode.EGRESS_NOT_ALLOWED
    assert stub.calls == []


def test_no_parameter_template_succeeds_without_egress(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(
        db_session,
        db_client,
        fingerprint="fp-noparam",
        stable_key="pex_noparam",
        sql_text="SELECT 1 FROM dual",
        parameter_schema=[],
        name="상수 조회",
        description="파라미터 없음",
    )
    stub = _stub(_extraction())
    result = extract_query_parameters(
        db_session,
        ParameterExtractionRequest(
            source_name=SOURCE_A["source_name"],
            template_id=detail["id"],
            version_id=detail["current_version_id"],
            request_text="anything",
        ),
        llm_provider=stub,
        settings=_settings(allow_raw=False),
    )
    assert result.needs_clarification is False
    assert result.resolved_parameters == {}
    assert stub.calls == []


def test_prompt_includes_request_excludes_sql(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(db_session, db_client, stable_key="pex_prompt")
    stub = _stub(
        _extraction(
            values=[
                {"name": "ward_cd", "value": "A01"},
                {"name": "from_date", "value": "2026-09-01"},
            ]
        )
    )
    raw = f"{SYNTHETIC} A01 병동 2026-09-01"
    extract_query_parameters(
        db_session,
        ParameterExtractionRequest(
            source_name=SOURCE_A["source_name"],
            template_id=detail["id"],
            version_id=detail["current_version_id"],
            request_text=raw,
        ),
        llm_provider=stub,
        settings=_settings(allow_raw=True),
    )
    blob = "\n".join(message.content for message in stub.calls[0].messages)
    assert raw in blob
    assert "SELECT 1 FROM dual" not in blob
    assert "DELETE" not in blob
    assert "ward_cd" in blob
    assert "password" not in blob.casefold()
    assert "not mentioned in request_text" in blob
    assert "omit it from both" in blob
    payload = json.loads(stub.calls[0].messages[1].content)
    assert payload["request_text"] == raw
    assert "sql_text" not in payload
    assert stub.calls[0].purpose == LLMRequestPurpose.PARAMETER_EXTRACTION


def test_hallucinated_parameter_fail_closed(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(db_session, db_client, stable_key="pex_halluc")
    stub = _stub(
        _extraction(values=[{"name": "unknown_parameter", "value": "X"}])
    )
    with pytest.raises(ParameterExtractionError) as exc_info:
        extract_query_parameters(
            db_session,
            ParameterExtractionRequest(
                source_name=SOURCE_A["source_name"],
                template_id=detail["id"],
                version_id=detail["current_version_id"],
                request_text="x",
            ),
            llm_provider=stub,
            settings=_settings(allow_raw=True),
        )
    assert exc_info.value.code == ParameterExtractionErrorCode.LLM_OUTPUT_INVALID


def test_invalid_extracted_value_is_clarification_not_http_error(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(db_session, db_client, stable_key="pex_invalid")
    stub = _stub(
        _extraction(
            values=[
                {"name": "ward_cd", "value": 12},
                {"name": "from_date", "value": "2026-09-01"},
            ]
        )
    )
    result = extract_query_parameters(
        db_session,
        ParameterExtractionRequest(
            source_name=SOURCE_A["source_name"],
            template_id=detail["id"],
            version_id=detail["current_version_id"],
            request_text="x",
        ),
        llm_provider=stub,
        settings=_settings(allow_raw=True),
    )
    assert result.needs_clarification is True
    assert any(issue.code == ISSUE_TYPE_MISMATCH for issue in result.issues)
    assert "12" not in (result.clarification_question or "")


def test_missing_required_clarification(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(db_session, db_client, stable_key="pex_missing")
    stub = _stub(_extraction(values=[{"name": "ward_cd", "value": "A01"}]))
    result = extract_query_parameters(
        db_session,
        ParameterExtractionRequest(
            source_name=SOURCE_A["source_name"],
            template_id=detail["id"],
            version_id=detail["current_version_id"],
            request_text="x",
        ),
        llm_provider=stub,
        settings=_settings(allow_raw=True),
    )
    assert result.needs_clarification is True
    assert any(issue.code == ISSUE_MISSING_REQUIRED for issue in result.issues)
    assert "시작일" in (result.clarification_question or "")


def test_llm_schema_rejects_null_and_object_value() -> None:
    with pytest.raises(ValidationError):
        LLMParameterExtraction(
            values=[LLMExtractedParameter(name="a", value=None)],
            unresolved_parameter_names=[],
        )
    with pytest.raises(ValidationError):
        LLMParameterExtraction(
            values=[LLMExtractedParameter(name="a", value={"x": 1})],
            unresolved_parameter_names=[],
        )


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_api_success_and_cache_headers(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = _create_eligible(db_session, db_client, stable_key="pex_api")
    stub = _stub(
        _extraction(
            values=[
                {"name": "ward_cd", "value": "A01"},
                {"name": "from_date", "value": "2026-09-01"},
            ]
        )
    )

    def _wrapped(session: Session, request: ParameterExtractionRequest, **kwargs: Any):
        return extract_query_parameters(
            session,
            request,
            llm_provider=stub,
            settings=_settings(allow_raw=True),
        )

    monkeypatch.setattr(
        "app.api.routes.parameter_extraction.extract_query_parameters", _wrapped
    )
    response = db_client.post(
        "/api/v1/query-parameters/extract",
        json={
            "source_name": SOURCE_A["source_name"],
            "template_id": detail["id"],
            "version_id": detail["current_version_id"],
            "request_text": f"{SYNTHETIC} A01 2026-09-01",
        },
    )
    assert response.status_code == 200, response.text
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert response.headers.get("Pragma") == "no-cache"
    body = response.json()
    assert body["needs_clarification"] is False
    assert body["resolved_parameters"]["ward_cd"] == "A01"


def test_api_egress_forbidden_by_default(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(
        db_session, db_client, fingerprint="fp-api-egress", stable_key="pex_api_egress"
    )
    response = db_client.post(
        "/api/v1/query-parameters/extract",
        json={
            "source_name": SOURCE_A["source_name"],
            "template_id": detail["id"],
            "version_id": detail["current_version_id"],
            "request_text": "A01",
        },
    )
    assert response.status_code == 403
    assert (
        response.json()["detail"]["code"]
        == ParameterExtractionErrorCode.EGRESS_NOT_ALLOWED
    )


def test_api_validation_errors(db_client: TestClient) -> None:
    assert (
        db_client.post(
            "/api/v1/query-parameters/extract",
            json={
                "source_name": " ",
                "template_id": 1,
                "version_id": 1,
                "request_text": "x",
            },
        ).status_code
        == 422
    )
    assert (
        db_client.post(
            "/api/v1/query-parameters/extract",
            json={
                "source_name": SOURCE_A["source_name"],
                "template_id": 0,
                "version_id": 1,
                "request_text": "x",
            },
        ).status_code
        == 422
    )


def test_provider_timeout_maps_to_unavailable(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_eligible(
        db_session, db_client, fingerprint="fp-to", stable_key="pex_to"
    )
    stub = StubLLMProvider(
        error=LLMProviderError(LLMProviderErrorCode.TIMEOUT, "timed out")
    )
    with pytest.raises(ParameterExtractionError) as exc_info:
        extract_query_parameters(
            db_session,
            ParameterExtractionRequest(
                source_name=SOURCE_A["source_name"],
                template_id=detail["id"],
                version_id=detail["current_version_id"],
                request_text="x",
            ),
            llm_provider=stub,
            settings=_settings(allow_raw=True),
        )
    assert exc_info.value.code == ParameterExtractionErrorCode.LLM_UNAVAILABLE
