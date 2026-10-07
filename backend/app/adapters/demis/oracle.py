"""Oracle read-only DEMIS adapter (python-oracledb thin mode).

Production-selectable when ``dbms_type=oracle``. Never logs or embeds host,
DSN, username, password, SQL text, parameter values, or result rows.
Does not require Oracle Instant Client (thick mode is not used).
"""

from __future__ import annotations

import time
from typing import Any

import oracledb
from pydantic import ValidationError

from app.adapters.demis.credentials import CredentialMaterial
from app.adapters.demis.errors import (
    DemisAdapterError,
    DemisAdapterErrorCode,
    DemisProbeState,
)
from app.adapters.demis.profile import ConnectionProfileSnapshot
from app.adapters.demis.types import (
    DemisAdapterDiagnostics,
    ReadonlyQueryRequest,
    ReadonlyQueryResult,
)

_PROBE_TIMEOUT_SECONDS = 5
_READONLY_PROBE_SQL = "SELECT 1 FROM DUAL"

_SANITIZED_CONNECT_FAILED = "DEMIS read-only connection could not be established"
_SANITIZED_TIMEOUT = "DEMIS read-only query execution timed out"
_SANITIZED_EXECUTION_FAILED = "DEMIS read-only query execution failed"
_SANITIZED_INVALID_REQUEST = "readonly query request is invalid"
_SANITIZED_NOT_CONFIGURED = "Oracle DEMIS adapter profile is incomplete"


class OracleReadOnlyDemisAdapter:
    """Concrete ``ReadOnlyDemisAdapter`` for Oracle via python-oracledb thin mode."""

    def __init__(
        self,
        profile: ConnectionProfileSnapshot,
        credential: CredentialMaterial,
        *,
        connect: Any | None = None,
    ) -> None:
        # Optional ``connect`` is a test seam only; production uses oracledb.connect.
        self._profile = profile
        self._credential = credential
        self._connect = connect or oracledb.connect
        self._require_connect_inputs()

    def diagnostics(self) -> DemisAdapterDiagnostics:
        # Configuration-level only — no hidden live connectivity probe.
        return DemisAdapterDiagnostics(
            configured=True,
            dbms_type="oracle",
            live_connection_tested=False,
            reachable=None,
            read_only=None,
            failure_category=None,
        )

    def probe_readonly(self) -> DemisAdapterDiagnostics:
        """Explicit read-only live probe (fixed server-side timeout; no caller SQL)."""
        connection: Any | None = None
        cursor: Any | None = None
        phase = "connect"
        try:
            connection = self._open_connection(_PROBE_TIMEOUT_SECONDS)
            connection.autocommit = False
            connection.call_timeout = int(_PROBE_TIMEOUT_SECONDS) * 1000
            cursor = connection.cursor()
            phase = "read_only"
            cursor.execute("SET TRANSACTION READ ONLY")
            phase = "execute"
            cursor.execute(_READONLY_PROBE_SQL)
            # Discard probe row — never return, log, or persist result values.
            cursor.fetchone()
            return DemisAdapterDiagnostics(
                configured=True,
                dbms_type="oracle",
                live_connection_tested=True,
                reachable=True,
                read_only=True,
                failure_category=None,
            )
        except DemisAdapterError as exc:
            raise self._with_probe_state(exc, phase) from None
        except Exception as exc:
            raise self._with_probe_state(self._map_failure(phase, exc), phase) from None
        finally:
            self._cleanup(connection, cursor)

    def execute_readonly(self, request: ReadonlyQueryRequest) -> ReadonlyQueryResult:
        try:
            validated = (
                request
                if isinstance(request, ReadonlyQueryRequest)
                else ReadonlyQueryRequest.model_validate(request)
            )
        except ValidationError:
            raise DemisAdapterError(
                DemisAdapterErrorCode.INVALID_REQUEST,
                _SANITIZED_INVALID_REQUEST,
            ) from None

        connection: Any | None = None
        cursor: Any | None = None
        started = time.perf_counter()
        phase = "connect"

        try:
            connection = self._open_connection(validated.timeout_seconds)
            # Never enable autocommit for read-only DEMIS execution.
            connection.autocommit = False
            # Driver call timeout in milliseconds.
            connection.call_timeout = int(validated.timeout_seconds) * 1000

            cursor = connection.cursor()

            phase = "read_only"
            # Read-only transaction before any application SELECT.
            cursor.execute("SET TRANSACTION READ ONLY")

            phase = "execute"
            # Bound parameters only — never interpolate values into SQL text.
            cursor.execute(validated.sql_text, validated.parameters)

            phase = "fetch"
            fetch_limit = validated.row_limit + 1
            fetched = cursor.fetchmany(fetch_limit)
            truncated = len(fetched) > validated.row_limit
            limited = fetched[: validated.row_limit]

            columns = self._columns_from_cursor(cursor)
            rows = [self._row_to_dict(columns, row) for row in limited]
            elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))

            return ReadonlyQueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                truncated=truncated,
                elapsed_ms=elapsed_ms,
            )
        except DemisAdapterError:
            raise
        except Exception as exc:
            raise self._map_failure(phase, exc) from None
        finally:
            self._cleanup(connection, cursor)

    def _require_connect_inputs(self) -> None:
        profile = self._profile
        if (
            not profile.host
            or profile.port is None
            or not profile.database_name
            or not profile.username
            or not self._credential.get_secret()
        ):
            raise DemisAdapterError(
                DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED,
                _SANITIZED_NOT_CONFIGURED,
            )

    def _open_connection(self, timeout_seconds: int) -> Any:
        profile = self._profile
        # Thin-mode connect kwargs only. Never build a logged DSN string.
        try:
            return self._connect(
                user=profile.username,
                password=self._credential.get_secret(),
                host=profile.host,
                port=int(profile.port) if profile.port is not None else None,
                service_name=profile.database_name,
                tcp_connect_timeout=float(timeout_seconds),
            )
        except DemisAdapterError:
            raise
        except Exception as exc:
            raise self._map_failure("connect", exc) from None

    @staticmethod
    def _columns_from_cursor(cursor: Any) -> list[str]:
        description = getattr(cursor, "description", None)
        if not description:
            return []
        columns: list[str] = []
        for item in description:
            name = item[0] if item else None
            columns.append(str(name) if name is not None else "")
        return columns

    @staticmethod
    def _row_to_dict(columns: list[str], row: Any) -> dict[str, Any]:
        values = list(row)
        mapped: dict[str, Any] = {}
        for index, column in enumerate(columns):
            mapped[column] = values[index] if index < len(values) else None
        return mapped

    @staticmethod
    def _cleanup(connection: Any | None, cursor: Any | None) -> None:
        # Prefer rollback over commit. Cleanup failures must not mask primary errors.
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass
        if connection is not None:
            try:
                connection.rollback()
            except Exception:
                pass
            try:
                connection.close()
            except Exception:
                pass

    @staticmethod
    def _with_probe_state(exc: DemisAdapterError, phase: str) -> DemisAdapterError:
        if phase == "connect":
            probe = DemisProbeState(
                live_connection_tested=True,
                reachable=False,
                read_only=None,
            )
        elif phase == "read_only":
            probe = DemisProbeState(
                live_connection_tested=True,
                reachable=True,
                read_only=False,
            )
        else:
            # SELECT probe (and fetch) run only after read-only txn succeeds.
            probe = DemisProbeState(
                live_connection_tested=True,
                reachable=True,
                read_only=True,
            )
        return DemisAdapterError(exc.code, str(exc), probe=probe)

    @staticmethod
    def _map_failure(phase: str, exc: BaseException) -> DemisAdapterError:
        if phase == "connect":
            code = DemisAdapterErrorCode.CONNECTION_FAILED
            message = _SANITIZED_CONNECT_FAILED
        elif OracleReadOnlyDemisAdapter._looks_like_timeout(exc):
            code = DemisAdapterErrorCode.TIMEOUT
            message = _SANITIZED_TIMEOUT
        elif phase in {"read_only", "execute", "fetch"}:
            code = DemisAdapterErrorCode.EXECUTION_FAILED
            message = _SANITIZED_EXECUTION_FAILED
        else:
            code = DemisAdapterErrorCode.EXECUTION_FAILED
            message = _SANITIZED_EXECUTION_FAILED
        # Do not chain driver exceptions — messages may contain SQL/DSN details.
        return DemisAdapterError(code, message)

    @staticmethod
    def _looks_like_timeout(exc: BaseException) -> bool:
        type_name = type(exc).__name__.casefold()
        if "timeout" in type_name:
            return True
        # Inspect bounded driver error codes only; never copy message text outward.
        args = getattr(exc, "args", ())
        if not args:
            return False
        first = args[0]
        code = getattr(first, "code", None)
        full_code = str(getattr(first, "full_code", "") or "").casefold()
        # Common oracledb / Oracle timeout indicators (code-only checks).
        if code in {1013, 3113, 3114}:  # ORA-01013 / connection lost variants
            return "timeout" in full_code or code == 1013
        if "dpy-4011" in full_code or "dpy-4012" in full_code:
            return True
        return False
