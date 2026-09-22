import { apiGet } from "./client";
import type {
  CatalogActiveSummary,
  CatalogCategoryListResponse,
  CatalogColumnListResponse,
  CatalogIndexListResponse,
  CatalogRelationListResponse,
  CatalogTableDetailResponse,
  CatalogTableListResponse,
} from "../types/catalog";

export function listActiveCatalogs(): Promise<CatalogActiveSummary[]> {
  return apiGet<CatalogActiveSummary[]>("/catalog/active");
}

export function getActiveCatalog(sourceName: string): Promise<CatalogActiveSummary> {
  return apiGet<CatalogActiveSummary>(`/catalog/active/${encodeURIComponent(sourceName)}`);
}

export function listTables(
  sourceName: string,
  params: {
    q?: string;
    schema_name?: string;
    category?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<CatalogTableListResponse> {
  return apiGet<CatalogTableListResponse>(
    `/catalog/active/${encodeURIComponent(sourceName)}/tables`,
    params,
  );
}

export function getTableDetail(
  sourceName: string,
  schemaName: string,
  tableName: string,
): Promise<CatalogTableDetailResponse> {
  return apiGet<CatalogTableDetailResponse>(
    `/catalog/active/${encodeURIComponent(sourceName)}/tables/${encodeURIComponent(schemaName)}/${encodeURIComponent(tableName)}`,
  );
}

export function listColumns(
  sourceName: string,
  params: {
    q?: string;
    schema_name?: string;
    table_name?: string;
    is_primary_key?: boolean;
    is_unique?: boolean;
    nullable?: boolean;
    limit?: number;
    offset?: number;
  } = {},
): Promise<CatalogColumnListResponse> {
  return apiGet<CatalogColumnListResponse>(
    `/catalog/active/${encodeURIComponent(sourceName)}/columns`,
    params,
  );
}

export function listRelations(
  sourceName: string,
  params: {
    schema_name?: string;
    table_name?: string;
    referenced_table_name?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<CatalogRelationListResponse> {
  return apiGet<CatalogRelationListResponse>(
    `/catalog/active/${encodeURIComponent(sourceName)}/relations`,
    params,
  );
}

export function listIndexes(
  sourceName: string,
  params: {
    schema_name?: string;
    table_name?: string;
    unique?: boolean;
    limit?: number;
    offset?: number;
  } = {},
): Promise<CatalogIndexListResponse> {
  return apiGet<CatalogIndexListResponse>(
    `/catalog/active/${encodeURIComponent(sourceName)}/indexes`,
    params,
  );
}

export function listCategories(
  sourceName: string,
  params: {
    q?: string;
    limit?: number;
    offset?: number;
  } = {},
): Promise<CatalogCategoryListResponse> {
  return apiGet<CatalogCategoryListResponse>(
    `/catalog/active/${encodeURIComponent(sourceName)}/categories`,
    params,
  );
}
