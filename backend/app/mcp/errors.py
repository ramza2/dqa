"""Sanitized public error contracts for MCP Discovery tools (Phase 28-B).

Reuses the same reviewed code/message pairs as the Data Discovery and Catalog
Query HTTP APIs. Never forward exception text, SQL, secrets, or patient data.
"""

from __future__ import annotations

import json
from typing import Mapping, NoReturn

from mcp.server.fastmcp.exceptions import ToolError

from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode
from app.api.public_errors import PublicErrorSpec

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
_FALLBACK_DISCOVERY = PublicErrorSpec(500, "data discovery request failed")
_FALLBACK_CATALOG = PublicErrorSpec(500, "catalog metadata query failed")


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
