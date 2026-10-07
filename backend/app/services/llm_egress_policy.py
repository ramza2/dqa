"""Central fail-closed policy for data sent to an LLM provider."""

from __future__ import annotations

from enum import Enum

from app.core.config import Settings
from app.schemas.llm import LLMRequestPurpose


class LLMEgressPayloadClass(str, Enum):
    """Data classes that may cross the DQA -> LLM trust boundary."""

    METADATA_ONLY = "metadata_only"
    RAW_REQUEST_TEXT = "raw_request_text"
    QUERY_RESULT_ROWS = "query_result_rows"


def is_llm_egress_allowed(
    settings: Settings,
    *,
    purpose: LLMRequestPurpose,
    payload_class: LLMEgressPayloadClass,
) -> bool:
    """Return whether the requested LLM egress is explicitly allowed.

    Unknown/future combinations fail closed.
    Query-result rows are never allowed by the current policy.
    """

    if payload_class == LLMEgressPayloadClass.QUERY_RESULT_ROWS:
        return False

    if payload_class == LLMEgressPayloadClass.METADATA_ONLY:
        return purpose in {
            LLMRequestPurpose.TEMPLATE_RECOMMENDATION,
            LLMRequestPurpose.CATALOG_EXPLANATION,
        }

    if payload_class == LLMEgressPayloadClass.RAW_REQUEST_TEXT:
        return (
            purpose == LLMRequestPurpose.PARAMETER_EXTRACTION
            and settings.llm_parameter_extraction_allow_raw_request
            and settings.llm_parameter_extraction_raw_request_egress_approved
        )

    return False
