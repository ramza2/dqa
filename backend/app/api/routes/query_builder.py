"""Operator-only graphical query preview; never executes against DEMIS."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.adapters.db.deps import get_db_session
from app.auth.dependencies import require_permission
from app.auth.models import AuthenticatedActor, Permission
from app.schemas.catalog_preview import CatalogPreviewRequest, CatalogPreviewResponse
from app.services.catalog_preview import CatalogPreviewError, preview_catalog_query

router = APIRouter(prefix="/api/v1/query-builder", tags=["query-builder"])

@router.post("/preview", response_model=CatalogPreviewResponse)
def preview(
    body: CatalogPreviewRequest,
    response: Response,
    session: Session = Depends(get_db_session),
    _actor: AuthenticatedActor = Depends(require_permission(Permission.QUERY_OPERATE)),
) -> CatalogPreviewResponse:
    response.headers["Cache-Control"] = "no-store, private"
    response.headers["Pragma"] = "no-cache"
    try:
        return preview_catalog_query(session, body)
    except CatalogPreviewError as exc:
        if exc.code == "ACTIVE_CATALOG_NOT_FOUND":
            status = 404
        elif exc.code == "CATALOG_MISMATCH":
            status = 409
        else:
            status = 422
        raise HTTPException(
            status_code=status,
            detail={"code": exc.code, "message": "Query preview unavailable; verify Catalog selection."},
        ) from None
