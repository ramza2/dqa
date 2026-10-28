import { apiPost } from "./client";
import type { CatalogPreviewRequest, CatalogPreviewResponse } from "../types/queryBuilder";

export function previewCatalogQuery(request: CatalogPreviewRequest): Promise<CatalogPreviewResponse> {
  return apiPost<CatalogPreviewRequest, CatalogPreviewResponse>(
    "/query-builder/preview", request,
  );
}
