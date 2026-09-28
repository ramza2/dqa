"""Schemas for Query Template recommendation (no parameter extraction / execution)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Routing confidence threshold (template match routing — not clinical confidence).
RECOMMENDATION_MIN_CONFIDENCE = 0.70
MAX_RECOMMENDATION_CANDIDATES = 20
MAX_RANKED_TEMPLATE_IDS = 20
MAX_REQUEST_TEXT_LENGTH = 2000
MAX_SOURCE_NAME_LENGTH = 255

NO_MATCH_CLARIFICATION = (
    "조회하려는 업무나 데이터 범위를 조금 더 구체적으로 입력해주세요."
)


class TemplateRecommendationRequest(BaseModel):
    """Natural-language recommendation request (raw text stays local)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_name: str = Field(min_length=1, max_length=MAX_SOURCE_NAME_LENGTH)
    request_text: str = Field(min_length=1, max_length=MAX_REQUEST_TEXT_LENGTH)

    @field_validator("source_name", "request_text")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class RecommendedTemplate(BaseModel):
    """Candidate / recommended template metadata (no SQL text)."""

    model_config = ConfigDict(extra="forbid")

    template_id: int
    version_id: int
    version: int
    stable_key: str
    name: str
    description: str | None = None
    target_schemas: list[str]
    parameter_names: list[str] = Field(default_factory=list)
    parameter_count: int = 0


class TemplateRecommendationResponse(BaseModel):
    """Recommendation or clarification outcome (advisory only; not execution permission)."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    catalog_revision_id: int
    schema_fingerprint: str
    needs_clarification: bool
    clarification_question: str | None = None
    # Template routing confidence (0..1). Not clinical / diagnostic confidence.
    confidence: float | None = None
    reason: str | None = None
    recommended_template: RecommendedTemplate | None = None
    ranked_candidates: list[RecommendedTemplate] = Field(default_factory=list)


class LLMTemplateRanking(BaseModel):
    """Strict structured ranking output from the LLM (untrusted until validated)."""

    model_config = ConfigDict(extra="forbid")

    recommended_template_id: int | None = None
    ranked_template_ids: list[int] = Field(default_factory=list, max_length=MAX_RANKED_TEMPLATE_IDS)
    confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool
    clarification_question: str | None = None
    reason: str | None = None

    @field_validator("ranked_template_ids")
    @classmethod
    def no_duplicate_ids(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("ranked_template_ids must not contain duplicates")
        return value
