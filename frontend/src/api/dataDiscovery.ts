import { apiGet, apiPost } from "./client";
import type {
  DataDiscoveryEmbeddingSyncResponse,
  DataDiscoveryIndexStatusResponse,
  DataDiscoveryRebuildResponse,
  DataDiscoverySearchRequest,
  DataDiscoverySearchResponse,
} from "../types/dataDiscovery";

export function searchDataDiscovery(
  request: DataDiscoverySearchRequest,
  init?: RequestInit,
): Promise<DataDiscoverySearchResponse> {
  return apiPost<DataDiscoverySearchRequest, DataDiscoverySearchResponse>(
    "/data-discovery/search",
    request,
    init,
  );
}

export function getDataDiscoveryIndexStatus(
  sourceName: string,
  init?: RequestInit,
): Promise<DataDiscoveryIndexStatusResponse> {
  return apiGet<DataDiscoveryIndexStatusResponse>(
    `/data-discovery/${encodeURIComponent(sourceName)}/index-status`,
    undefined,
    init,
  );
}

export function rebuildDataDiscoveryDocuments(
  sourceName: string,
  init?: RequestInit,
): Promise<DataDiscoveryRebuildResponse> {
  return apiPost<Record<string, never>, DataDiscoveryRebuildResponse>(
    `/data-discovery/${encodeURIComponent(sourceName)}/documents/rebuild`,
    {},
    init,
  );
}

export function syncDataDiscoveryEmbeddings(
  sourceName: string,
  init?: RequestInit,
): Promise<DataDiscoveryEmbeddingSyncResponse> {
  return apiPost<Record<string, never>, DataDiscoveryEmbeddingSyncResponse>(
    `/data-discovery/${encodeURIComponent(sourceName)}/embeddings/sync`,
    {},
    init,
  );
}
