"""Test-only fake ReadOnlyDemisAdapter and credential resolver.

Never selectable through the production factory. Not a DEMIS driver.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from app.adapters.demis.credentials import CredentialMaterial
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.demis.types import (
    DemisAdapterDiagnostics,
    ReadonlyQueryRequest,
    ReadonlyQueryResult,
)


class FakeCredentialResolver:
    """In-memory credential resolver for tests only."""

    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._mapping = dict(mapping or {})

    def put(self, secret_ref: str, secret: str) -> None:
        self._mapping[secret_ref] = secret

    def resolve(self, credential_secret_ref: str) -> CredentialMaterial:
        if not credential_secret_ref or credential_secret_ref not in self._mapping:
            raise DemisAdapterError(
                DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
                "credential reference could not be resolved",
            )
        secret = self._mapping[credential_secret_ref]
        if not secret:
            raise DemisAdapterError(
                DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE,
                "credential reference resolved to empty material",
            )
        return CredentialMaterial(secret_ref=credential_secret_ref, _secret=secret)


class FakeReadOnlyDemisAdapter:
    """In-memory read-only adapter for contract tests.

    - Does not generate or modify SQL
    - Stores SQL and parameters separately (no interpolation)
    - Enforces timeout_seconds / row_limit from the request contract
    - Never logs result rows
    """

    def __init__(
        self,
        *,
        dbms_type: str = "fake",
        configured: bool = True,
        rows: list[dict[str, Any]] | None = None,
        columns: list[str] | None = None,
        simulate_timeout: bool = False,
        simulate_execution_failure: bool = False,
        elapsed_ms: int = 1,
    ) -> None:
        self._dbms_type = dbms_type
        self._configured = configured
        self._seed_rows = list(rows or [])
        if columns is not None:
            self._columns = list(columns)
        elif self._seed_rows:
            self._columns = list(self._seed_rows[0].keys())
        else:
            self._columns = []
        self._simulate_timeout = simulate_timeout
        self._simulate_execution_failure = simulate_execution_failure
        self._elapsed_ms = max(0, elapsed_ms)
        self.last_sql_text: str | None = None
        self.last_parameters: dict[str, Any] | None = None
        self.last_timeout_seconds: int | None = None
        self.last_row_limit: int | None = None

    def diagnostics(self) -> DemisAdapterDiagnostics:
        return DemisAdapterDiagnostics(
            configured=self._configured,
            dbms_type=self._dbms_type,
            live_connection_tested=False,
            reachable=None,
            read_only=None,
            failure_category=(
                None
                if self._configured
                else DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED
            ),
        )

    def execute_readonly(self, request: ReadonlyQueryRequest) -> ReadonlyQueryResult:
        try:
            validated = (
                request
                if isinstance(request, ReadonlyQueryRequest)
                else ReadonlyQueryRequest.model_validate(request)
            )
        except ValidationError as exc:
            raise DemisAdapterError(
                DemisAdapterErrorCode.INVALID_REQUEST,
                "readonly query request is invalid",
            ) from exc

        # Bound-parameter contract: keep SQL and parameters separate. Never
        # interpolate parameter values into sql_text.
        self.last_sql_text = validated.sql_text
        self.last_parameters = dict(validated.parameters)
        self.last_timeout_seconds = validated.timeout_seconds
        self.last_row_limit = validated.row_limit

        if self._simulate_timeout:
            raise DemisAdapterError(
                DemisAdapterErrorCode.TIMEOUT,
                "read-only query execution timed out",
            )
        if self._simulate_execution_failure:
            raise DemisAdapterError(
                DemisAdapterErrorCode.EXECUTION_FAILED,
                "read-only query execution failed",
            )

        started = time.perf_counter()
        limited = self._seed_rows[: validated.row_limit]
        truncated = len(self._seed_rows) > validated.row_limit
        wall_ms = int((time.perf_counter() - started) * 1000)
        elapsed = max(self._elapsed_ms, wall_ms)

        return ReadonlyQueryResult(
            columns=list(self._columns),
            rows=list(limited),
            row_count=len(limited),
            truncated=truncated,
            elapsed_ms=elapsed,
        )


def build_fake_readonly_demis_adapter(**kwargs: Any) -> FakeReadOnlyDemisAdapter:
    """Explicit test helper — never used by the production factory."""
    return FakeReadOnlyDemisAdapter(**kwargs)
