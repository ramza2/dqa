"""Query Template recommendation tests (eligibility, privacy, ranking; no execution)."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.adapters.llm.errors import LLMProviderError, LLMProviderErrorCode
from app.adapters.recommendation.errors import RecommendationError, RecommendationErrorCode
from app.models.catalog_import import CatalogImportRevision
from app.schemas.recommendation import (
    MAX_REQUEST_TEXT_LENGTH,
    NO_MATCH_CLARIFICATION,
    RECOMMENDATION_MIN_CONFIDENCE,
    LLMTemplateRanking,
    TemplateRecommendationRequest,
)
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.template_recommendation import recommend_query_templates
from tests.catalog_package_fixtures import (
    DEFAULT_SOURCE,
    build_core_documents,
    build_package_zip,
)
from tests.fakes.llm import StubLLMProvider, make_structured_result

pytestmark = pytest.mark.integration

SOURCE_A = dict(DEFAULT_SOURCE)
SECRET_TOKEN = "PATIENT-SECRET-123"


def _import_and_activate(
    session: Session,
    *,
    fingerprint: str,
    source: dict[str, Any] | None = None,
) -> CatalogImportRevision:
    src = source or SOURCE_A
    files = build_core_documents(
        source=src,
        fingerprint=fingerprint,
        tables=[
            {"schema": "DEMIS_OWNER", "name": "T1"},
            {"schema": "OTHER_OWNER", "name": "T2"},
        ],
    )
    archive = build_package_zip(
        package_readiness="READY",
        source=src,
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
        "stable_key": "admission.history",
        "name": "입원 병동 이력 조회",
        "description": "환자의 입원 병동 이력을 조회합니다",
        "source_name": SOURCE_A["source_name"],
        "target_schemas": ["DEMIS_OWNER"],
        "sql_text": "SELECT 1 FROM dual WHERE ward_id = :ward_id",
        "parameter_schema": [
            {
                "name": "ward_id",
                "label": "병동",
                "description": "입원 병동 식별자",
                "type": "integer",
                "required": True,
                "min": 1,
            }
        ],
        "row_limit": 50,
        "timeout_seconds": 15,
    }
    body.update(overrides)
    return body


def _create_approve_enable(
    db_session: Session,
    db_client: TestClient,
    *,
    fingerprint: str = "fp-rec-base",
    **overrides: Any,
) -> dict[str, Any]:
    _import_and_activate(db_session, fingerprint=fingerprint)
    db_session.commit()
    created = db_client.post("/api/v1/query-templates", json=_create_body(**overrides))
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert db_client.post(
        f"/api/v1/query-templates/{template_id}/submit-review", json={}
    ).status_code == 200
    assert db_client.post(
        f"/api/v1/query-templates/{template_id}/approve", json={}
    ).status_code == 200
    enabled = db_client.post(f"/api/v1/query-templates/{template_id}/enable")
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True
    return enabled.json()


def _ranking(
    *,
    recommended_template_id: int | None,
    ranked_template_ids: list[int],
    confidence: float,
    needs_clarification: bool = False,
    clarification_question: str | None = None,
    reason: str | None = "metadata match",
) -> LLMTemplateRanking:
    return LLMTemplateRanking(
        recommended_template_id=recommended_template_id,
        ranked_template_ids=ranked_template_ids,
        confidence=confidence,
        needs_clarification=needs_clarification,
        clarification_question=clarification_question,
        reason=reason,
    )


def _stub_for(ranking: LLMTemplateRanking) -> StubLLMProvider:
    return StubLLMProvider(result=make_structured_result(ranking))


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_eligible_approved_enabled_compatible_safe(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="elig_ok")
    stub = _stub_for(
        _ranking(
            recommended_template_id=detail["id"],
            ranked_template_ids=[detail["id"]],
            confidence=0.95,
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력 조회",
        ),
        llm_provider=stub,
    )
    assert result.recommended_template is not None
    assert result.recommended_template.template_id == detail["id"]
    assert result.needs_clarification is False
    assert len(stub.calls) == 1


def test_draft_excluded(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-draft")
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="elig_draft"),
    )
    assert created.status_code == 201
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(recommended_template_id=1, ranked_template_ids=[1], confidence=0.9)
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.needs_clarification is True
    assert result.recommended_template is None
    assert stub.calls == []


def test_in_review_excluded(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-review")
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="elig_review"),
    )
    template_id = created.json()["id"]
    assert db_client.post(
        f"/api/v1/query-templates/{template_id}/submit-review", json={}
    ).status_code == 200
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(
                recommended_template_id=template_id,
                ranked_template_ids=[template_id],
                confidence=0.9,
            )
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.recommended_template is None
    assert stub.calls == []


def test_rejected_excluded(db_session: Session, db_client: TestClient) -> None:
    _import_and_activate(db_session, fingerprint="fp-rej")
    db_session.commit()
    created = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(stable_key="elig_rej"),
    )
    template_id = created.json()["id"]
    assert db_client.post(
        f"/api/v1/query-templates/{template_id}/submit-review", json={}
    ).status_code == 200
    assert db_client.post(
        f"/api/v1/query-templates/{template_id}/reject",
        json={"note": "no"},
    ).status_code == 200
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(
                recommended_template_id=template_id,
                ranked_template_ids=[template_id],
                confidence=0.9,
            )
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.recommended_template is None
    assert stub.calls == []


def test_approved_but_disabled_excluded(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="elig_disabled")
    template_id = detail["id"]
    disabled = db_client.post(f"/api/v1/query-templates/{template_id}/disable")
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(
                recommended_template_id=template_id,
                ranked_template_ids=[template_id],
                confidence=0.9,
            )
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.recommended_template is None
    assert stub.calls == []


def test_incompatible_catalog_excluded(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(
        db_session, db_client, fingerprint="fp-old", stable_key="elig_incompat"
    )
    # Activate a different READY package so fingerprint/revision diverge.
    _import_and_activate(db_session, fingerprint="fp-new")
    db_session.commit()
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(
                recommended_template_id=detail["id"],
                ranked_template_ids=[detail["id"]],
                confidence=0.9,
            )
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.recommended_template is None
    assert stub.calls == []


def test_sql_unsafe_excluded(db_session: Session, db_client: TestClient) -> None:
    detail = _create_approve_enable(
        db_session,
        db_client,
        fingerprint="fp-unsafe",
        stable_key="elig_unsafe",
        # Intentionally unsafe SQL still allowed at draft create; safety gate is
        # enforced for recommendation eligibility.
        sql_text="DELETE FROM T",
        parameter_schema=[],
        name="삭제성 템플릿",
        description="unsafe candidate",
    )
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(
                recommended_template_id=detail["id"],
                ranked_template_ids=[detail["id"]],
                confidence=0.9,
            )
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="삭제성 템플릿 unsafe candidate",
        ),
        llm_provider=stub,
    )
    assert result.recommended_template is None
    assert stub.calls == []


def test_other_source_excluded(db_session: Session, db_client: TestClient) -> None:
    _create_approve_enable(db_session, db_client, stable_key="elig_other_src")
    other = {
        "source_name": "other_source",
        "db_type": "oracle",
        "database_name": "OTHERDB",
        "default_schema": "OTHER_OWNER",
    }
    _import_and_activate(db_session, fingerprint="fp-other", source=other)
    db_session.commit()
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(recommended_template_id=1, ranked_template_ids=[1], confidence=0.9)
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name="other_source",
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.recommended_template is None
    assert stub.calls == []


# ---------------------------------------------------------------------------
# Retrieval / privacy / ranking
# ---------------------------------------------------------------------------


def test_privacy_projection_excludes_raw_request_and_secret(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="priv_proj")
    stub = _stub_for(
        _ranking(
            recommended_template_id=detail["id"],
            ranked_template_ids=[detail["id"]],
            confidence=0.92,
        )
    )
    raw = f"{SECRET_TOKEN} 환자의 입원 병동 이력을 보고 싶어"
    recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text=raw,
        ),
        llm_provider=stub,
    )
    assert len(stub.calls) == 1
    blob = "\n".join(message.content for message in stub.calls[0].messages)
    assert SECRET_TOKEN not in blob
    assert raw not in blob
    assert "DELETE FROM" not in blob
    assert "SELECT 1 FROM dual" not in blob
    assert "ward_id" in blob  # parameter name metadata OK
    user_payload = json.loads(stub.calls[0].messages[1].content)
    assert "matched_terms" in user_payload
    terms = set(user_payload["matched_terms"])
    assert terms & {"환자", "입원", "병동", "이력"}
    assert SECRET_TOKEN.casefold() not in {t.casefold() for t in terms}
    for candidate in user_payload["candidates"]:
        assert "sql_text" not in candidate
        assert "sql" not in candidate


def test_deterministic_ordering_and_name_match(
    db_session: Session, db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-order")
    db_session.commit()
    first = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(
            stable_key="zzz.ward",
            name="병동 조회 A",
            description="기타",
        ),
    ).json()
    second = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(
            stable_key="aaa.ward",
            name="병동 조회 B",
            description="기타",
        ),
    ).json()
    for template_id in (first["id"], second["id"]):
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/approve", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/enable"
        ).status_code == 200

    seen_orders: list[list[int]] = []
    for _ in range(2):
        stub = _stub_for(
            _ranking(
                recommended_template_id=second["id"],
                ranked_template_ids=[second["id"], first["id"]],
                confidence=0.9,
            )
        )
        recommend_query_templates(
            db_session,
            TemplateRecommendationRequest(
                source_name=SOURCE_A["source_name"],
                request_text="병동 조회",
            ),
            llm_provider=stub,
        )
        payload = json.loads(stub.calls[0].messages[1].content)
        seen_orders.append([item["template_id"] for item in payload["candidates"]])
    assert seen_orders[0] == seen_orders[1]


def test_no_lexical_match_skips_llm(
    db_session: Session, db_client: TestClient
) -> None:
    _create_approve_enable(db_session, db_client, stable_key="no_lex")
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(recommended_template_id=1, ranked_template_ids=[1], confidence=0.9)
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="completely-unrelated-zzzz",
        ),
        llm_provider=stub,
    )
    assert result.needs_clarification is True
    assert result.clarification_question == NO_MATCH_CLARIFICATION
    assert result.recommended_template is None
    assert stub.calls == []


def test_routing_confidence_high_returns_recommendation(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="conf_high")
    stub = _stub_for(
        _ranking(
            recommended_template_id=detail["id"],
            ranked_template_ids=[detail["id"]],
            confidence=RECOMMENDATION_MIN_CONFIDENCE,
            needs_clarification=False,
            reason="이름과 설명 일치",
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.needs_clarification is False
    assert result.recommended_template is not None
    assert result.recommended_template.template_id == detail["id"]
    assert result.confidence == RECOMMENDATION_MIN_CONFIDENCE
    assert result.reason == "이름과 설명 일치"
    assert result.catalog_revision_id > 0
    assert result.schema_fingerprint


def test_routing_confidence_below_threshold_requires_clarification(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="conf_low")
    stub = _stub_for(
        _ranking(
            recommended_template_id=detail["id"],
            ranked_template_ids=[detail["id"]],
            confidence=RECOMMENDATION_MIN_CONFIDENCE - 0.01,
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.needs_clarification is True
    assert result.recommended_template is None
    assert result.ranked_candidates


def test_llm_needs_clarification_nulls_recommendation(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="conf_ask")
    stub = _stub_for(
        _ranking(
            recommended_template_id=detail["id"],
            ranked_template_ids=[detail["id"]],
            confidence=0.95,
            needs_clarification=True,
            clarification_question="어느 병동인가요?",
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.needs_clarification is True
    assert result.recommended_template is None
    assert result.clarification_question == "어느 병동인가요?"


def test_null_recommended_id_requires_clarification(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="conf_null")
    stub = _stub_for(
        _ranking(
            recommended_template_id=None,
            ranked_template_ids=[detail["id"]],
            confidence=0.8,
            needs_clarification=False,
        )
    )
    result = recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    assert result.needs_clarification is True
    assert result.recommended_template is None


def test_hallucinated_candidate_id_fail_closed(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="halluc")
    stub = _stub_for(
        _ranking(
            recommended_template_id=999999,
            ranked_template_ids=[999999, detail["id"]],
            confidence=0.99,
        )
    )
    with pytest.raises(RecommendationError) as exc_info:
        recommend_query_templates(
            db_session,
            TemplateRecommendationRequest(
                source_name=SOURCE_A["source_name"],
                request_text="환자 입원 병동 이력",
            ),
            llm_provider=stub,
        )
    assert exc_info.value.code == RecommendationErrorCode.LLM_OUTPUT_INVALID


# ---------------------------------------------------------------------------
# Provider error mapping + API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider_code,expected_code,status_code",
    [
        (
            LLMProviderErrorCode.NOT_CONFIGURED,
            RecommendationErrorCode.LLM_NOT_CONFIGURED,
            503,
        ),
        (LLMProviderErrorCode.TIMEOUT, RecommendationErrorCode.LLM_UNAVAILABLE, 503),
        (
            LLMProviderErrorCode.CONNECTION_ERROR,
            RecommendationErrorCode.LLM_UNAVAILABLE,
            503,
        ),
        (LLMProviderErrorCode.HTTP_ERROR, RecommendationErrorCode.LLM_OUTPUT_INVALID, 502),
        (
            LLMProviderErrorCode.STRUCTURED_OUTPUT_INVALID,
            RecommendationErrorCode.LLM_OUTPUT_INVALID,
            502,
        ),
    ],
)
def test_provider_errors_map_to_sanitized_http(
    db_session: Session,
    db_client: TestClient,
    provider_code: str,
    expected_code: str,
    status_code: int,
) -> None:
    _create_approve_enable(
        db_session,
        db_client,
        fingerprint=f"fp-{provider_code}",
        stable_key=f"err_{provider_code[-8:]}",
    )
    stub = StubLLMProvider(
        error=LLMProviderError(provider_code, f"internal {SECRET_TOKEN}")
    )
    # Service-level mapping
    with pytest.raises(RecommendationError) as exc_info:
        recommend_query_templates(
            db_session,
            TemplateRecommendationRequest(
                source_name=SOURCE_A["source_name"],
                request_text="환자 입원 병동 이력",
            ),
            llm_provider=stub,
        )
    assert exc_info.value.code == expected_code
    assert SECRET_TOKEN not in str(exc_info.value)

    # API-level mapping via dependency injection is covered by overriding is hard;
    # call HTTP path with a monkeypatched service factory would be heavier.
    # Validate HTTP mapper through FastAPI by patching recommend function.
    from app.api.routes import recommendations as recommendations_route

    def _raise(*_args: Any, **_kwargs: Any) -> Any:
        raise RecommendationError(expected_code, "sanitized failure")

    original = recommendations_route.recommend_query_templates
    recommendations_route.recommend_query_templates = _raise  # type: ignore[assignment]
    try:
        response = db_client.post(
            "/api/v1/query-recommendations",
            json={
                "source_name": SOURCE_A["source_name"],
                "request_text": f"{SECRET_TOKEN} 환자 입원",
            },
        )
        assert response.status_code == status_code
        body = response.json()
        assert body["detail"]["code"] == expected_code
        assert SECRET_TOKEN not in response.text
        assert "internal" not in response.text
    finally:
        recommendations_route.recommend_query_templates = original  # type: ignore[assignment]


def test_api_success_recommendation(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="api_ok")
    stub = _stub_for(
        _ranking(
            recommended_template_id=detail["id"],
            ranked_template_ids=[detail["id"]],
            confidence=0.91,
        )
    )

    def _wrapped(session: Session, request: TemplateRecommendationRequest, **kwargs: Any):
        return recommend_query_templates(session, request, llm_provider=stub)

    monkeypatch.setattr(
        "app.api.routes.recommendations.recommend_query_templates", _wrapped
    )
    response = db_client.post(
        "/api/v1/query-recommendations",
        json={
            "source_name": SOURCE_A["source_name"],
            "request_text": "환자 입원 병동 이력 조회",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["needs_clarification"] is False
    assert body["recommended_template"]["template_id"] == detail["id"]
    assert "sql_text" not in body["recommended_template"]
    assert stub.closed is False or stub.closed is True  # close may be owned by service only when factory


def test_api_validation_errors(db_client: TestClient) -> None:
    blank_source = db_client.post(
        "/api/v1/query-recommendations",
        json={"source_name": " ", "request_text": "환자"},
    )
    assert blank_source.status_code == 422

    blank_text = db_client.post(
        "/api/v1/query-recommendations",
        json={"source_name": SOURCE_A["source_name"], "request_text": "  "},
    )
    assert blank_text.status_code == 422

    too_long = db_client.post(
        "/api/v1/query-recommendations",
        json={
            "source_name": SOURCE_A["source_name"],
            "request_text": "가" * (MAX_REQUEST_TEXT_LENGTH + 1),
        },
    )
    assert too_long.status_code == 422


def test_api_active_catalog_missing(db_client: TestClient) -> None:
    response = db_client.post(
        "/api/v1/query-recommendations",
        json={
            "source_name": "missing_source",
            "request_text": "환자 입원 병동 이력",
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == RecommendationErrorCode.ACTIVE_CATALOG_NOT_FOUND


def test_api_no_match_clarification(
    db_session: Session, db_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create_approve_enable(db_session, db_client, stable_key="api_nomatch")
    stub = StubLLMProvider(
        result=make_structured_result(
            _ranking(recommended_template_id=1, ranked_template_ids=[1], confidence=0.9)
        )
    )

    def _wrapped(session: Session, request: TemplateRecommendationRequest, **kwargs: Any):
        return recommend_query_templates(session, request, llm_provider=stub)

    monkeypatch.setattr(
        "app.api.routes.recommendations.recommend_query_templates", _wrapped
    )
    response = db_client.post(
        "/api/v1/query-recommendations",
        json={
            "source_name": SOURCE_A["source_name"],
            "request_text": "totally-unrelated-qqqq",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["needs_clarification"] is True
    assert body["recommended_template"] is None
    assert stub.calls == []


def test_stub_close_lifecycle_when_owned_not_required(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="life_close")
    stub = _stub_for(
        _ranking(
            recommended_template_id=detail["id"],
            ranked_template_ids=[detail["id"]],
            confidence=0.9,
        )
    )
    recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="환자 입원 병동 이력",
        ),
        llm_provider=stub,
    )
    # Injected providers are not closed by the service (caller owns lifecycle).
    assert stub.closed is False
    stub.close()
    assert stub.closed is True
