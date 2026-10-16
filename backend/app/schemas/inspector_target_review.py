"""Sanitized, read-only review of two independent target configurations.

This API never approves, binds, probes, connects or stores an Inspector target.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

InspectorConfigState = Literal[
    "DISABLED", "ENV_BLOCKED", "INVALID", "CONFIGURED_UNVERIFIED",
]
InspectorComparisonState = Literal[
    "NOT_COMPARABLE", "TARGET_METADATA_MISMATCH", "STRUCTURAL_MATCH_UNVERIFIED",
]
InspectorMismatchField = Literal[
    "environment", "source_name", "dbms_type", "host", "port",
    "database_name_vs_service_name", "username",
]


class InspectorTargetReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: int
    inspector_configuration_state: InspectorConfigState
    comparison_state: InspectorComparisonState
    mismatch_fields: list[InspectorMismatchField]
    profile_enabled: bool
    # Explicit negative authority; these are deliberately never input flags.
    inspector_bound_to_profile: Literal[False] = False
    connection_authorized: Literal[False] = False
    live_connection_tested: Literal[False] = False
    credential_values_resolved: Literal[False] = False
