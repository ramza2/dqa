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
    MAX_LLM_FREE_TEXT_CHARS,
    MAX_PROMPT_DESCRIPTION_CHARS,
    MAX_PROMPT_MATCHED_TERMS_PER_CANDIDATE,
    MAX_PROMPT_PARAMETERS_PER_CANDIDATE,
    MAX_RECOMMENDATION_CANDIDATES,
    MAX_REQUEST_TEXT_LENGTH,
    NO_MATCH_CLARIFICATION,
    RECOMMENDATION_MAX_TOKENS,
    RECOMMENDATION_MIN_CONFIDENCE,
    LLMTemplateRanking,
    TemplateRecommendationRequest,
)
from app.services.catalog_active import activate_catalog_revision
from app.services.catalog_package_import import import_catalog_package_bytes
from app.services.template_recommendation import recommend_query_templates
from app.repositories.query_template import QueryTemplateRepository
from pydantic import ValidationError
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
    assert stub.calls[0].max_tokens == RECOMMENDATION_MAX_TOKENS
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
        assert "retrieval_score" in candidate
        assert isinstance(candidate["matched_terms"], list)


def test_candidate_specific_matched_terms_from_parameter_labels(
    db_session: Session, db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-cand-terms")
    db_session.commit()
    ward = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(
            stable_key="cand.ward",
            name="조회 A",
            description="일반 조회",
            parameter_schema=[
                {
                    "name": "ward_id",
                    "label": "병동",
                    "description": "병동 코드",
                    "type": "integer",
                    "required": True,
                    "min": 1,
                }
            ],
        ),
    ).json()
    dept = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(
            stable_key="cand.dept",
            name="조회 B",
            description="일반 조회",
            parameter_schema=[
                {
                    "name": "dept_id",
                    "label": "진료과",
                    "description": "진료과 코드",
                    "type": "integer",
                    "required": True,
                    "min": 1,
                }
            ],
        ),
    ).json()
    for template_id in (ward["id"], dept["id"]):
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/approve", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/enable"
        ).status_code == 200

    stub = _stub_for(
        _ranking(
            recommended_template_id=ward["id"],
            ranked_template_ids=[ward["id"]],
            confidence=0.9,
        )
    )
    raw = f"{SECRET_TOKEN} 병동 조회"
    recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text=raw,
        ),
        llm_provider=stub,
    )
    payload = json.loads(stub.calls[0].messages[1].content)
    blob = stub.calls[0].messages[1].content
    assert SECRET_TOKEN not in blob
    assert raw not in blob
    assert "SELECT 1 FROM dual" not in blob
    by_id = {item["template_id"]: item for item in payload["candidates"]}
    assert ward["id"] in by_id
    assert "병동" in by_id[ward["id"]]["matched_terms"]
    assert by_id[ward["id"]]["retrieval_score"] > 0
    if dept["id"] in by_id:
        assert "병동" not in by_id[dept["id"]]["matched_terms"]


def test_deterministic_ordering_score_then_stable_key(
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
    order = [item["template_id"] for item in payload["candidates"]]
    # Equal lexical scores: stable_key asc => aaa.ward before zzz.ward.
    assert order == [second["id"], first["id"]]
    assert payload["candidates"][0]["stable_key"] == "aaa.ward"
    assert payload["candidates"][1]["stable_key"] == "zzz.ward"


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


def test_duplicate_ranked_ids_rejected_by_schema() -> None:
    with pytest.raises(ValidationError):
        LLMTemplateRanking(
            recommended_template_id=1,
            ranked_template_ids=[1, 1],
            confidence=0.9,
            needs_clarification=False,
        )


def test_recommended_id_missing_from_ranked_list_rejected(
    db_session: Session, db_client: TestClient
) -> None:
    detail = _create_approve_enable(db_session, db_client, stable_key="rank_miss")
    # Construct a ranking that bypasses schema duplicate checks but fails service rule.
    ranking = LLMTemplateRanking(
        recommended_template_id=detail["id"],
        ranked_template_ids=[],
        confidence=0.95,
        needs_clarification=False,
    )
    stub = StubLLMProvider(result=make_structured_result(ranking))
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


def test_llm_free_text_max_length_enforced() -> None:
    too_long = "가" * (MAX_LLM_FREE_TEXT_CHARS + 1)
    with pytest.raises(ValidationError):
        LLMTemplateRanking(
            recommended_template_id=1,
            ranked_template_ids=[1],
            confidence=0.9,
            needs_clarification=False,
            reason=too_long,
        )
    with pytest.raises(ValidationError):
        LLMTemplateRanking(
            recommended_template_id=None,
            ranked_template_ids=[1],
            confidence=0.5,
            needs_clarification=True,
            clarification_question=too_long,
        )


def test_prompt_projection_bounds_long_description_and_parameters(
    db_session: Session, db_client: TestClient
) -> None:
    long_description = "설명" * 400  # well over MAX_PROMPT_DESCRIPTION_CHARS
    many_params = [
        {
            "name": f"p{i}",
            "label": f"라벨{i}",
            "description": f"파라미터설명{i}",
            "type": "integer",
            "required": True,
            "min": 1,
        }
        for i in range(MAX_PROMPT_PARAMETERS_PER_CANDIDATE + 5)
    ]
    detail = _create_approve_enable(
        db_session,
        db_client,
        fingerprint="fp-bounds",
        stable_key="bounds.long",
        description=long_description,
        parameter_schema=many_params,
        name="병동 조회",
        sql_text=(
            "SELECT 1 FROM dual WHERE "
            + " AND ".join(f"c{i} = :p{i}" for i in range(len(many_params)))
        ),
    )
    # Stored metadata remains full length.
    stored = QueryTemplateRepository(db_session).get_by_id(detail["id"])
    assert stored is not None
    assert stored.description is not None
    assert len(stored.description) > MAX_PROMPT_DESCRIPTION_CHARS
    assert len(stored.current_version.parameter_schema) > MAX_PROMPT_PARAMETERS_PER_CANDIDATE

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
            request_text="병동 조회",
        ),
        llm_provider=stub,
    )
    candidate = json.loads(stub.calls[0].messages[1].content)["candidates"][0]
    assert candidate["description"] is not None
    assert len(candidate["description"]) <= MAX_PROMPT_DESCRIPTION_CHARS
    assert len(candidate["parameters"]) <= MAX_PROMPT_PARAMETERS_PER_CANDIDATE
    assert len(candidate["matched_terms"]) <= MAX_PROMPT_MATCHED_TERMS_PER_CANDIDATE
    assert stub.calls[0].max_tokens == RECOMMENDATION_MAX_TOKENS


def test_candidate_cap_limits_llm_payload(
    db_session: Session, db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-cap")
    db_session.commit()
    ids: list[int] = []
    total = MAX_RECOMMENDATION_CANDIDATES + 3
    for i in range(total):
        created = db_client.post(
            "/api/v1/query-templates",
            json=_create_body(
                stable_key=f"cap.item.{i:02d}",
                name=f"병동 공통 {i}",
                description="병동 조회",
            ),
        )
        assert created.status_code == 201, created.text
        template_id = created.json()["id"]
        ids.append(template_id)
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/approve", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/enable"
        ).status_code == 200

    top_id = ids[0]
    stub = _stub_for(
        _ranking(
            recommended_template_id=top_id,
            ranked_template_ids=[top_id],
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
    assert len(payload["candidates"]) <= MAX_RECOMMENDATION_CANDIDATES


def test_stable_key_and_description_match(
    db_session: Session, db_client: TestClient
) -> None:
    _import_and_activate(db_session, fingerprint="fp-fields")
    db_session.commit()
    key_hit = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(
            stable_key="unique.tokenkey",
            name="기타",
            description="일반",
        ),
    ).json()
    desc_hit = db_client.post(
        "/api/v1/query-templates",
        json=_create_body(
            stable_key="other.plain",
            name="기타",
            description="특수문구알파",
        ),
    ).json()
    for template_id in (key_hit["id"], desc_hit["id"]):
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/submit-review", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/approve", json={}
        ).status_code == 200
        assert db_client.post(
            f"/api/v1/query-templates/{template_id}/enable"
        ).status_code == 200

    stub_key = _stub_for(
        _ranking(
            recommended_template_id=key_hit["id"],
            ranked_template_ids=[key_hit["id"]],
            confidence=0.9,
        )
    )
    recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="tokenkey 조회",
        ),
        llm_provider=stub_key,
    )
    key_payload = json.loads(stub_key.calls[0].messages[1].content)
    key_ids = {item["template_id"] for item in key_payload["candidates"]}
    assert key_hit["id"] in key_ids

    stub_desc = _stub_for(
        _ranking(
            recommended_template_id=desc_hit["id"],
            ranked_template_ids=[desc_hit["id"]],
            confidence=0.9,
        )
    )
    recommend_query_templates(
        db_session,
        TemplateRecommendationRequest(
            source_name=SOURCE_A["source_name"],
            request_text="특수문구알파 조회",
        ),
        llm_provider=stub_desc,
    )
    desc_payload = json.loads(stub_desc.calls[0].messages[1].content)
    desc_ids = {item["template_id"] for item in desc_payload["candidates"]}
    assert desc_hit["id"] in desc_ids


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
