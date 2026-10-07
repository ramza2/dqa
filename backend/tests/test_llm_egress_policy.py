"""LLM data-egress policy unit tests."""

from app.core.config import Settings
from app.schemas.llm import LLMRequestPurpose
from app.services.llm_egress_policy import (
    LLMEgressPayloadClass,
    is_llm_egress_allowed,
)


def _settings(*, allow_raw: bool = False, approved: bool = False) -> Settings:
    return Settings(
        APP_ENV="test",
        LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST=allow_raw,
        LLM_PARAMETER_EXTRACTION_RAW_REQUEST_EGRESS_APPROVED=approved,
    )


def test_metadata_only_recommendation_is_allowed() -> None:
    assert is_llm_egress_allowed(
        _settings(),
        purpose=LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
        payload_class=LLMEgressPayloadClass.METADATA_ONLY,
    )


def test_raw_request_requires_both_opt_in_and_approval() -> None:
    for allow_raw, approved in [
        (False, False),
        (True, False),
        (False, True),
    ]:
        assert not is_llm_egress_allowed(
            _settings(allow_raw=allow_raw, approved=approved),
            purpose=LLMRequestPurpose.PARAMETER_EXTRACTION,
            payload_class=LLMEgressPayloadClass.RAW_REQUEST_TEXT,
        )

    assert is_llm_egress_allowed(
        _settings(allow_raw=True, approved=True),
        purpose=LLMRequestPurpose.PARAMETER_EXTRACTION,
        payload_class=LLMEgressPayloadClass.RAW_REQUEST_TEXT,
    )


def test_query_result_rows_are_never_allowed() -> None:
    for purpose in LLMRequestPurpose:
        assert not is_llm_egress_allowed(
            _settings(allow_raw=True, approved=True),
            purpose=purpose,
            payload_class=LLMEgressPayloadClass.QUERY_RESULT_ROWS,
        )
