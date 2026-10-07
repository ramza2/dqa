"""Typed sanitized errors for the DEMIS read-only adapter boundary."""

from __future__ import annotations

from dataclasses import dataclass


class DemisAdapterErrorCode:
    """Bounded failure categories for future execution / audit mapping.

    Messages and payloads must never include host, port, username, database/
    service name, credential references, DSN, driver text, or result rows.
    """

    ADAPTER_NOT_CONFIGURED = "ADAPTER_NOT_CONFIGURED"
    UNSUPPORTED_DBMS = "UNSUPPORTED_DBMS"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    TIMEOUT = "TIMEOUT"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    RESULT_LIMIT_ERROR = "RESULT_LIMIT_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    PROFILE_DISABLED = "PROFILE_DISABLED"


@dataclass(frozen=True)
class DemisAdapterIssue:
    code: str
    message: str


@dataclass(frozen=True)
class DemisProbeState:
    """Optional live-probe progress for explicit connection-test responses."""

    live_connection_tested: bool
    reachable: bool | None
    read_only: bool | None


class DemisAdapterError(Exception):
    """Sanitized adapter failure. Never embed secrets, DSN, or result rows."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        probe: DemisProbeState | None = None,
    ) -> None:
        self.issue = DemisAdapterIssue(code=code, message=message)
        self.probe = probe
        super().__init__(message)

    @property
    def code(self) -> str:
        return self.issue.code

    @property
    def failure_category(self) -> str:
        """Stable category suitable for audit / caller mapping."""
        return self.issue.code

    def __repr__(self) -> str:
        return f"DemisAdapterError(code={self.code!r}, message={str(self)!r})"
