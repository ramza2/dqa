"""Data Discovery adapter/error boundary (search orchestration + readiness)."""

from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode

__all__ = ["DataDiscoveryError", "DataDiscoveryErrorCode"]
