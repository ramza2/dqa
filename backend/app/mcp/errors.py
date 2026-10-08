"""Sanitized public error contracts for MCP Discovery + Template Query tools.

Reuses reviewed code/message pairs from Data Discovery, Catalog Query, and
Query Execution HTTP APIs. Never forward exception text, SQL, secrets, tokens,
or patient data.
"""

from __future__ import annotations

import json
from typing import Mapping, NoReturn

from mcp.server.fastmcp.exceptions import ToolError

from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode
from app.adapters.demis.errors import DemisAdapterError, DemisAdapterErrorCode
from app.adapters.execution.errors import (
    ExecutionError,
    ExecutionErrorCode,
    ExecutionPreviewError,
    ExecutionPreviewErrorCode,
)
from app.api.public_errors import PublicErrorSpec
from app.mcp.execution_token import McpExecutionTokenError, McpExecutionTokenErrorCode

# Shared with HTTP Data Discovery / Catalog Query public contracts.
_MCP_PUBLIC_ERRORS: dict[str, PublicErrorSpec] = {
    CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND: PublicErrorSpec(
        404,
        "active catalog revision not found",
    ),
    CatalogQueryErrorCode.TABLE_NOT_FOUND: PublicErrorSpec(
        404,
        "catalog table not found",
    ),
    DataDiscoveryErrorCode.DISCOVERY_INDEX_NOT_READY: PublicErrorSpec(
        409,
        "discovery documents are not ready for the active catalog revision",
    ),
    DataDiscoveryErrorCode.EMBEDDING_NOT_CONFIGURED: PublicErrorSpec(
        503,
        "embedding provider is not configured",
    ),
    DataDiscoveryErrorCode.EMBEDDING_NOT_READY: PublicErrorSpec(
        409,
        "embeddings are not ready for the active catalog revision",
    ),
    DataDiscoveryErrorCode.EMBEDDING_TIMEOUT: PublicErrorSpec(
        504,
        "embedding provider request timed out",
    ),
    DataDiscoveryErrorCode.EMBEDDING_CONNECTION_FAILED: PublicErrorSpec(
        502,
        "embedding provider connection failed",
    ),
    DataDiscoveryErrorCode.EMBEDDING_HTTP_ERROR: PublicErrorSpec(
        502,
        "embedding provider returned an error",
    ),
    DataDiscoveryErrorCode.EMBEDDING_INVALID_RESPONSE: PublicErrorSpec(
        502,
        "embedding provider returned an invalid response",
    ),
    DataDiscoveryErrorCode.EMBEDDING_DIMENSION_MISMATCH: PublicErrorSpec(
        503,
        "embedding dimension is not supported",
    ),
    DataDiscoveryErrorCode.INVALID_SEARCH_MODE: PublicErrorSpec(
        422,
        "invalid search mode",
    ),
    DataDiscoveryErrorCode.INVALID_OBJECT_TYPE: PublicErrorSpec(
        422,
        "invalid object type",
    ),
}

_INVALID_INPUT = PublicErrorSpec(422, "invalid mcp tool arguments")
_REVISION_CHANGED = PublicErrorSpec(
    409,
    "active catalog revision changed during describe_resource",
)
_FALLBACK_DISCOVERY = PublicErrorSpec(500, "data discovery request failed")
_FALLBACK_CATALOG = PublicErrorSpec(500, "catalog metadata query failed")

# Stable public code for mid-request active-revision mismatch (fail closed).
MCP_CATALOG_REVISION_CHANGED = "MCP_CATALOG_REVISION_CHANGED"

_MCP_EXECUTION_PUBLIC_ERRORS: dict[str, PublicErrorSpec] = {
    ExecutionPreviewErrorCode.TEMPLATE_NOT_FOUND: PublicErrorSpec(
        404, "query template not found"
    ),
    ExecutionPreviewErrorCode.ACTIVE_CATALOG_NOT_FOUND: PublicErrorSpec(
        404, "active catalog revision not found"
    ),
    ExecutionPreviewErrorCode.CONNECTION_PROFILE_NOT_FOUND: PublicErrorSpec(
        404, "connection profile not found"
    ),
    ExecutionPreviewErrorCode.TEMPLATE_NOT_ELIGIBLE: PublicErrorSpec(
        409, "query template is not eligible for execution"
    ),
    ExecutionPreviewErrorCode.STALE_TEMPLATE_VERSION: PublicErrorSpec(
        409, "requested template version is stale"
    ),
    ExecutionPreviewErrorCode.CATALOG_MISMATCH: PublicErrorSpec(
        409, "query template is incompatible with the active catalog"
    ),
    ExecutionPreviewErrorCode.CONNECTION_PROFILE_DISABLED: PublicErrorSpec(
        409, "connection profile is disabled"
    ),
    ExecutionPreviewErrorCode.CONNECTION_PROFILE_INCOMPLETE: PublicErrorSpec(
        409, "connection profile is incomplete"
    ),
    ExecutionPreviewErrorCode.SQL_UNSAFE: PublicErrorSpec(
        422, "query template SQL does not pass safety validation"
    ),
    ExecutionPreviewErrorCode.PARAMETER_SCHEMA_INVALID: PublicErrorSpec(
        422, "query template parameter schema is invalid"
    ),
    ExecutionPreviewErrorCode.PARAMETER_UNDECLARED: PublicErrorSpec(
        422, "request contains an undeclared parameter"
    ),
    ExecutionPreviewErrorCode.PARAMETER_INVALID: PublicErrorSpec(
        422, "query parameter values are invalid"
    ),
    ExecutionErrorCode.AUDIT_UNAVAILABLE: PublicErrorSpec(
        503, "query audit is unavailable"
    ),
    ExecutionErrorCode.DEMIS_ADAPTER_UNAVAILABLE: PublicErrorSpec(
        503, "DEMIS read-only adapter is unavailable"
    ),
    DemisAdapterErrorCode.TIMEOUT: PublicErrorSpec(
        504, "DEMIS read-only query execution timed out"
    ),
    DemisAdapterErrorCode.UNSUPPORTED_DBMS: PublicErrorSpec(
        503, "DEMIS database type is not supported"
    ),
    DemisAdapterErrorCode.CREDENTIAL_UNAVAILABLE: PublicErrorSpec(
        503, "DEMIS credential is unavailable"
    ),
    DemisAdapterErrorCode.CONNECTION_FAILED: PublicErrorSpec(
        503, "DEMIS read-only connection could not be established"
    ),
    DemisAdapterErrorCode.ADAPTER_NOT_CONFIGURED: PublicErrorSpec(
        503, "DEMIS read-only adapter is not configured"
    ),
    DemisAdapterErrorCode.PROFILE_DISABLED: PublicErrorSpec(
        503, "DEMIS connection profile is disabled"
    ),
    DemisAdapterErrorCode.EXECUTION_FAILED: PublicErrorSpec(
        502, "DEMIS read-only query execution failed"
    ),
    DemisAdapterErrorCode.RESULT_LIMIT_ERROR: PublicErrorSpec(
        502, "DEMIS query result limit could not be enforced"
    ),
    DemisAdapterErrorCode.INVALID_REQUEST: PublicErrorSpec(
        422, "DEMIS read-only query request is invalid"
    ),
    McpExecutionTokenErrorCode.KEY_UNAVAILABLE: PublicErrorSpec(
        503, "mcp execution token key is not configured"
    ),
    McpExecutionTokenErrorCode.INVALID: PublicErrorSpec(
        401, "mcp execution token is invalid"
    ),
    McpExecutionTokenErrorCode.EXPIRED: PublicErrorSpec(
        401, "mcp execution token has expired"
    ),
    McpExecutionTokenErrorCode.SUBJECT_MISMATCH: PublicErrorSpec(
        403, "mcp execution token subject does not match the authenticated actor"
    ),
    "MCP_QUERY_EXECUTION_DISABLED": PublicErrorSpec(
        403, "mcp query execution is disabled"
    ),
    "MCP_EXECUTION_BINDING_MISMATCH": PublicErrorSpec(
        409, "execution token binding no longer matches current eligibility"
    ),
}

_FALLBACK_EXECUTION = PublicErrorSpec(500, "query execution request failed")
_CLARIFICATION_CODES = frozenset(
    {
        ExecutionPreviewErrorCode.PARAMETER_INVALID,
        ExecutionPreviewErrorCode.PARAMETER_UNDECLARED,
    }
)


def public_error_payload(
    *,
    error_code: str,
    contracts: Mapping[str, PublicErrorSpec],
    fallback_code: str,
    fallback: PublicErrorSpec,
) -> dict[str, str]:
    spec = contracts.get(error_code)
    if spec is None:
        return {"code": fallback_code, "message": fallback.message}
    return {"code": spec.public_code or error_code, "message": spec.message}


def raise_mcp_tool_error(payload: dict[str, str]) -> NoReturn:
    """Fail the tool call with a sanitized JSON error envelope (no internal text)."""
    raise ToolError(json.dumps({"error": payload}, separators=(",", ":")))


def raise_invalid_tool_arguments() -> NoReturn:
    raise_mcp_tool_error(
        {
            "code": "MCP_INVALID_TOOL_ARGUMENTS",
            "message": _INVALID_INPUT.message,
        }
    )


def raise_catalog_revision_changed() -> NoReturn:
    """Fail closed when metadata pages disagree on active revision identity."""
    raise_mcp_tool_error(
        {
            "code": MCP_CATALOG_REVISION_CHANGED,
            "message": _REVISION_CHANGED.message,
        }
    )


def raise_from_discovery_or_catalog_error(
    exc: DataDiscoveryError | CatalogQueryError,
) -> NoReturn:
    if isinstance(exc, CatalogQueryError):
        payload = public_error_payload(
            error_code=exc.code,
            contracts=_MCP_PUBLIC_ERRORS,
            fallback_code=CatalogQueryErrorCode.INTERNAL_ERROR,
            fallback=_FALLBACK_CATALOG,
        )
    else:
        payload = public_error_payload(
            error_code=exc.code,
            contracts=_MCP_PUBLIC_ERRORS,
            fallback_code="DATA_DISCOVERY_ERROR",
            fallback=_FALLBACK_DISCOVERY,
        )
    raise_mcp_tool_error(payload)


def raise_from_execution_error(
    exc: ExecutionPreviewError | ExecutionError | DemisAdapterError | McpExecutionTokenError,
) -> NoReturn:
    code = exc.code
    payload = public_error_payload(
        error_code=code,
        contracts=_MCP_EXECUTION_PUBLIC_ERRORS,
        fallback_code=ExecutionErrorCode.INTERNAL_ERROR,
        fallback=_FALLBACK_EXECUTION,
    )
    raise_mcp_tool_error(payload)


def raise_query_execution_disabled() -> NoReturn:
    raise_mcp_tool_error(
        public_error_payload(
            error_code="MCP_QUERY_EXECUTION_DISABLED",
            contracts=_MCP_EXECUTION_PUBLIC_ERRORS,
            fallback_code="MCP_QUERY_EXECUTION_DISABLED",
            fallback=_MCP_EXECUTION_PUBLIC_ERRORS["MCP_QUERY_EXECUTION_DISABLED"],
        )
    )


def raise_execution_binding_mismatch() -> NoReturn:
    raise_mcp_tool_error(
        public_error_payload(
            error_code="MCP_EXECUTION_BINDING_MISMATCH",
            contracts=_MCP_EXECUTION_PUBLIC_ERRORS,
            fallback_code="MCP_EXECUTION_BINDING_MISMATCH",
            fallback=_MCP_EXECUTION_PUBLIC_ERRORS["MCP_EXECUTION_BINDING_MISMATCH"],
        )
    )


def public_execution_error_payload(code: str) -> dict[str, str]:
    return public_error_payload(
        error_code=code,
        contracts=_MCP_EXECUTION_PUBLIC_ERRORS,
        fallback_code=ExecutionErrorCode.INTERNAL_ERROR,
        fallback=_FALLBACK_EXECUTION,
    )


def is_clarification_error(code: str) -> bool:
    return code in _CLARIFICATION_CODES
