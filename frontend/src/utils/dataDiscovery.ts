import { CatalogApiError } from "../types/catalog";

export function shortenFingerprint(value: string | null | undefined, keep = 12): string {
  if (!value) {
    return "—";
  }
  if (value.length <= keep * 2 + 1) {
    return value;
  }
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

export function shortenModelKey(value: string | null | undefined, keep = 8): string {
  if (!value) {
    return "—";
  }
  if (value.length <= keep * 2 + 1) {
    return value;
  }
  return `${value.slice(0, keep)}…${value.slice(-keep)}`;
}

export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return "—";
  }
  return value.toFixed(4);
}

export function formatRelationPathHop(hop: {
  from_schema: string;
  from_table: string;
  from_columns: string[];
  to_schema: string;
  to_table: string;
  to_columns: string[];
}): string {
  const fromCol = hop.from_columns[0] ?? "?";
  const toCol = hop.to_columns[0] ?? "?";
  return `${hop.from_schema}.${hop.from_table}.${fromCol} → ${hop.to_schema}.${hop.to_table}.${toCol}`;
}

export function formatDiscoveryError(error: unknown): string {
  if (error instanceof CatalogApiError) {
    if (error.status === 403 || error.code === "AUTHORIZATION_DENIED") {
      return "Administrator permission is required.";
    }
    if (error.status === 401) {
      return "Authentication is required.";
    }
    switch (error.code) {
      case "DISCOVERY_INDEX_NOT_READY":
        return "Open Index Status and rebuild discovery documents.";
      case "EMBEDDING_NOT_CONFIGURED":
        return "Keyword search is still available. Configure an embedding provider for Semantic/Hybrid.";
      case "EMBEDDING_NOT_READY":
        return "Open Index Status and sync embeddings.";
      case "CATALOG_ACTIVE_REVISION_NOT_FOUND":
        return "Active catalog revision not found for the selected source.";
      default:
        return error.message || `Request failed (${error.status}).`;
    }
  }
  return "Request failed.";
}

export const STALE_SEARCH_MESSAGE =
  "Catalog revision changed. Please run the search again.";

export const STALE_STATUS_MESSAGE =
  "Catalog revision changed. Please refresh index status.";
