"""Data Discovery HTTP API (Phase 27-C): search, index status, rebuild, sync."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.adapters.catalog.query_errors import CatalogQueryError, CatalogQueryErrorCode
from app.adapters.data_discovery.errors import DataDiscoveryError, DataDiscoveryErrorCode
from app.adapters.db.deps import get_db_session
from app.adapters.embedding.factory import create_embedding_provider
from app.api.public_errors import PublicErrorSpec, build_public_http_error
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.core.config import Settings, get_settings
from app.domain.data_discovery import DataDiscoverySearchMode
from app.repositories.data_discovery import DataDiscoveryRepository
from app.schemas.data_discovery import (
    DataDiscoveryEmbeddingCoverageModel,
    DataDiscoveryEmbeddingSyncResponse,
    DataDiscoveryIndexStatusResponse,
    DataDiscoveryRebuildResponse,
    DataDiscoverySearchRequest,
    DataDiscoverySearchResponse,
)
from app.services.catalog_query import resolve_active_revision
from app.services.data_discovery_document import rebuild_for_revision
from app.services.data_discovery_embedding import (
    embedding_status_for_revision,
    sync_embeddings_for_revision,
)
from app.services.data_discovery_search import search_schema

router = APIRouter(prefix="/api/v1/data-discovery", tags=["data-discovery"])

_PUBLIC_ERRORS = {
    CatalogQueryErrorCode.ACTIVE_REVISION_NOT_FOUND: PublicErrorSpec(
        status.HTTP_404_NOT_FOUND,
        "active catalog revision not found",
    ),
    DataDiscoveryErrorCode.DISCOVERY_INDEX_NOT_READY: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "discovery documents are not ready for the active catalog revision",
    ),
    DataDiscoveryErrorCode.EMBEDDING_NOT_CONFIGURED: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "embedding provider is not configured",
    ),
    DataDiscoveryErrorCode.EMBEDDING_NOT_READY: PublicErrorSpec(
        status.HTTP_409_CONFLICT,
        "embeddings are not ready for the active catalog revision",
    ),
    DataDiscoveryErrorCode.EMBEDDING_TIMEOUT: PublicErrorSpec(
        status.HTTP_504_GATEWAY_TIMEOUT,
        "embedding provider request timed out",
    ),
    DataDiscoveryErrorCode.EMBEDDING_CONNECTION_FAILED: PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "embedding provider connection failed",
    ),
    DataDiscoveryErrorCode.EMBEDDING_HTTP_ERROR: PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "embedding provider returned an error",
    ),
    DataDiscoveryErrorCode.EMBEDDING_INVALID_RESPONSE: PublicErrorSpec(
        status.HTTP_502_BAD_GATEWAY,
        "embedding provider returned an invalid response",
    ),
    DataDiscoveryErrorCode.EMBEDDING_DIMENSION_MISMATCH: PublicErrorSpec(
        status.HTTP_503_SERVICE_UNAVAILABLE,
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


def _discovery_http_error(exc: DataDiscoveryError | CatalogQueryError) -> HTTPException:
    return build_public_http_error(
        error_code=exc.code,
        contracts=_PUBLIC_ERRORS,
        fallback_code="DATA_DISCOVERY_ERROR",
        fallback_status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        fallback_message="data discovery request failed",
    )


def _coerce_mode(mode: object) -> DataDiscoverySearchMode:
    if isinstance(mode, DataDiscoverySearchMode):
        return mode
    return DataDiscoverySearchMode(str(mode))


@router.post("/search", response_model=DataDiscoverySearchResponse)
def post_search(
    request: DataDiscoverySearchRequest,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> DataDiscoverySearchResponse:
    """Search active Catalog schema metadata (keyword / semantic / hybrid)."""
    mode = _coerce_mode(request.mode)
    provider = None
    try:
        if mode in {DataDiscoverySearchMode.SEMANTIC, DataDiscoverySearchMode.HYBRID}:
            provider = create_embedding_provider(settings)
        return search_schema(
            session,
            request,
            embedding_provider=provider,
            settings=settings,
        )
    except (DataDiscoveryError, CatalogQueryError) as exc:
        raise _discovery_http_error(exc) from exc
    finally:
        if provider is not None:
            provider.close()


@router.get(
    "/{source_name}/index-status",
    response_model=DataDiscoveryIndexStatusResponse,
)
def get_index_status(
    source_name: str,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_READ)),
) -> DataDiscoveryIndexStatusResponse:
    """Return discovery document and embedding readiness (no embedding network calls)."""
    try:
        resolved = resolve_active_revision(session, source_name)
    except CatalogQueryError as exc:
        raise _discovery_http_error(exc) from exc

    document_count = DataDiscoveryRepository(session).count_for_revision(
        resolved.revision_id
    )
    document_state = "READY" if document_count > 0 else "NOT_READY"

    base_url = (settings.embedding_base_url or "").strip()
    model = (settings.embedding_model or "").strip()
    if not base_url or not model:
        return DataDiscoveryIndexStatusResponse(
            source_name=resolved.source_name,
            catalog_revision_id=resolved.revision_id,
            schema_fingerprint=resolved.schema_fingerprint,
            document_count=document_count,
            document_state=document_state,
            embedding_state="NOT_CONFIGURED",
        )

    provider = None
    try:
        provider = create_embedding_provider(settings)
        # model_key only — never call embed_* from this endpoint.
        model_key = provider.model_key
        coverage = embedding_status_for_revision(
            session, resolved.revision_id, model_key
        )
        embedding_state = "READY" if coverage.is_ready else "NOT_READY"
        return DataDiscoveryIndexStatusResponse(
            source_name=resolved.source_name,
            catalog_revision_id=resolved.revision_id,
            schema_fingerprint=resolved.schema_fingerprint,
            document_count=document_count,
            document_state=document_state,
            embedding_state=embedding_state,
            provider=provider.provider_name,
            model_name=provider.model_name,
            model_revision=provider.model_revision,
            model_key=model_key,
            dimension=provider.dimension,
            normalized=provider.normalized,
            coverage=DataDiscoveryEmbeddingCoverageModel(
                document_count=coverage.document_count,
                embedding_count=coverage.embedding_count,
                current_count=coverage.current_count,
                stale_count=coverage.stale_count,
                missing_count=coverage.missing_count,
            ),
        )
    except DataDiscoveryError as exc:
        return DataDiscoveryIndexStatusResponse(
            source_name=resolved.source_name,
            catalog_revision_id=resolved.revision_id,
            schema_fingerprint=resolved.schema_fingerprint,
            document_count=document_count,
            document_state=document_state,
            embedding_state="CONFIGURATION_ERROR",
            embedding_error_code=exc.code,
        )
    finally:
        if provider is not None:
            provider.close()


@router.post(
    "/{source_name}/documents/rebuild",
    response_model=DataDiscoveryRebuildResponse,
)
def post_rebuild_documents(
    source_name: str,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> DataDiscoveryRebuildResponse:
    """Rebuild discovery documents for the current active revision only."""
    try:
        resolved = resolve_active_revision(session, source_name)
        result = rebuild_for_revision(session, resolved.revision_id)
    except (DataDiscoveryError, CatalogQueryError) as exc:
        raise _discovery_http_error(exc) from exc
    return DataDiscoveryRebuildResponse(
        source_name=result.source_name,
        catalog_revision_id=result.catalog_import_revision_id,
        schema_fingerprint=result.schema_fingerprint,
        document_count=result.document_count,
        upserted_count=result.upserted_count,
        deleted_count=result.deleted_count,
        builder_version=result.builder_version,
    )


@router.post(
    "/{source_name}/embeddings/sync",
    response_model=DataDiscoveryEmbeddingSyncResponse,
)
def post_sync_embeddings(
    source_name: str,
    session: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.CATALOG_MANAGE)),
) -> DataDiscoveryEmbeddingSyncResponse:
    """Sync embeddings for the current active revision (explicit operator action)."""
    provider = None
    try:
        resolved = resolve_active_revision(session, source_name)
        document_count = DataDiscoveryRepository(session).count_for_revision(
            resolved.revision_id
        )
        if document_count <= 0:
            raise DataDiscoveryError(
                DataDiscoveryErrorCode.DISCOVERY_INDEX_NOT_READY,
                "discovery documents are not ready for the active catalog revision",
            )
        provider = create_embedding_provider(settings)
        sync_result = sync_embeddings_for_revision(
            session,
            resolved.revision_id,
            provider,
            batch_size=settings.embedding_batch_size,
        )
        coverage = embedding_status_for_revision(
            session, resolved.revision_id, provider.model_key
        )
        return DataDiscoveryEmbeddingSyncResponse(
            source_name=resolved.source_name,
            catalog_revision_id=resolved.revision_id,
            schema_fingerprint=resolved.schema_fingerprint,
            model_key=sync_result.model_key,
            document_count=sync_result.document_count,
            embedded_count=sync_result.embedded_count,
            skipped_count=sync_result.skipped_count,
            coverage=DataDiscoveryEmbeddingCoverageModel(
                document_count=coverage.document_count,
                embedding_count=coverage.embedding_count,
                current_count=coverage.current_count,
                stale_count=coverage.stale_count,
                missing_count=coverage.missing_count,
            ),
        )
    except (DataDiscoveryError, CatalogQueryError) as exc:
        raise _discovery_http_error(exc) from exc
    finally:
        if provider is not None:
            provider.close()
