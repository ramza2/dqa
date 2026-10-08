"""Deterministic Query Compiler domain contracts (Phase 29-C).

Compiler output is preview-only. It is not approved or executable production
authority and never opens DEMIS connections.
"""

from __future__ import annotations

from enum import StrEnum

COMPILER_VERSION = "1.0.0"

# Oracle unquoted/quoted identifier shape we accept from Catalog bindings.
# Rejects spaces, quotes, and injection-shaped fragments.
ORACLE_IDENT_PATTERN = r"^[A-Za-z][A-Za-z0-9_$#]{0,127}$"


class CompilerStatus(StrEnum):
    VALID = "VALID"
    INVALID = "INVALID"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    STALE = "STALE"


class CompilerIssueCode(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    STALE_MAPPING = "STALE_MAPPING"
    PLAN_INVALID = "PLAN_INVALID"
    SNAPSHOT_DRIFT = "SNAPSHOT_DRIFT"
    INVALID_IDENTIFIER = "INVALID_IDENTIFIER"
    ALIAS_COLLISION = "ALIAS_COLLISION"
    UNKNOWN_RESOURCE = "UNKNOWN_RESOURCE"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    UNKNOWN_RELATIONSHIP = "UNKNOWN_RELATIONSHIP"
    AMBIGUOUS_JOIN = "AMBIGUOUS_JOIN"
    UNSUPPORTED_OPERATOR = "UNSUPPORTED_OPERATOR"
    UNSUPPORTED_AGGREGATION = "UNSUPPORTED_AGGREGATION"
    UNSUPPORTED_SQL_SHAPE = "UNSUPPORTED_SQL_SHAPE"
    SQL_SAFETY_FAILED = "SQL_SAFETY_FAILED"
    COMPILATION_FAILED = "COMPILATION_FAILED"


__all__ = [
    "COMPILER_VERSION",
    "ORACLE_IDENT_PATTERN",
    "CompilerIssueCode",
    "CompilerStatus",
]
