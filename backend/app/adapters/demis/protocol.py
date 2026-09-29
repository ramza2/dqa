"""Read-only DEMIS adapter protocol (DBMS-neutral)."""

from __future__ import annotations

from typing import Protocol

from app.adapters.demis.types import (
    DemisAdapterDiagnostics,
    ReadonlyQueryRequest,
    ReadonlyQueryResult,
)


class ReadOnlyDemisAdapter(Protocol):
    """Application-facing DEMIS read-only execution boundary.

    Implementations must:
    - use bound parameters only (never interpolate values into SQL)
    - enforce statement timeout and row limit from the request
    - prefer read-only session/transaction when the DBMS supports it
    - execute exactly one statement per ``execute_readonly`` call
    - never generate or modify SQL
    - never call LLM, Query Template approval, or audit writers
    - never log or embed result rows / credentials in errors

    SQL Safety is assumed to have already passed; the adapter must not weaken it.
    """

    def diagnostics(self) -> DemisAdapterDiagnostics:
        """Return sanitized configuration / connectivity diagnostics."""
        ...

    def execute_readonly(self, request: ReadonlyQueryRequest) -> ReadonlyQueryResult:
        """Execute approved SQL with bound parameters under timeout/row limits."""
        ...
