"""Typed errors for Data Discovery search and embedding boundaries."""

from __future__ import annotations


class DataDiscoveryErrorCode:
    DISCOVERY_INDEX_NOT_READY = "DISCOVERY_INDEX_NOT_READY"
    EMBEDDING_NOT_CONFIGURED = "EMBEDDING_NOT_CONFIGURED"
    EMBEDDING_NOT_READY = "EMBEDDING_NOT_READY"
    EMBEDDING_TIMEOUT = "EMBEDDING_TIMEOUT"
    EMBEDDING_CONNECTION_FAILED = "EMBEDDING_CONNECTION_FAILED"
    EMBEDDING_HTTP_ERROR = "EMBEDDING_HTTP_ERROR"
    EMBEDDING_INVALID_RESPONSE = "EMBEDDING_INVALID_RESPONSE"
    EMBEDDING_DIMENSION_MISMATCH = "EMBEDDING_DIMENSION_MISMATCH"
    INVALID_SEARCH_MODE = "INVALID_SEARCH_MODE"
    INVALID_OBJECT_TYPE = "INVALID_OBJECT_TYPE"


class DataDiscoveryError(Exception):
    """Sanitized Data Discovery failure (no query text, secrets, or endpoints)."""

    def __init__(self, code: str, message: str, *, status_code: int | None = None) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(message)

    def __repr__(self) -> str:
        return (
            f"DataDiscoveryError(code={self.code!r}, status_code={self.status_code!r}, "
            f"message={str(self)!r})"
        )
