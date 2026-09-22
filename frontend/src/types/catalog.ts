/** Types mirrored from backend Pydantic schemas (catalog_package / catalog_query). */

export type PackageReadiness = "READY" | "WARNING" | "BLOCKED";

export interface CatalogActiveSummary {
  source_name: string;
  revision_id: number;
  schema_fingerprint: string;
  package_version: string;
  package_readiness: PackageReadiness;
  activated_at: string;
}

export interface CatalogQueryEnvelope<T> {
  source_name: string;
  revision_id: number;
  schema_fingerprint: string;
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export interface CatalogTableItem {
  schema_name: string;
  name: string;
  comment: string | null;
  table_type: string | null;
  category_ids: string[];
}

export type CatalogTableDetail = CatalogTableItem;

export interface CatalogTableDetailResponse {
  source_name: string;
  revision_id: number;
  schema_fingerprint: string;
  item: CatalogTableDetail;
}

export interface CatalogColumnItem {
  schema_name: string | null;
  table_name: string;
  name: string;
  ordinal: number | null;
  data_type: string | null;
  comment: string | null;
  nullable: boolean | null;
  is_primary_key: boolean | null;
  is_unique: boolean | null;
  default: string | null;
}

export interface CatalogRelationColumnMapping {
  column: string;
  referenced_column: string;
}

export interface CatalogRelationItem {
  name: string | null;
  schema_name: string | null;
  table_name: string;
  referenced_schema_name: string | null;
  referenced_table_name: string;
  columns: CatalogRelationColumnMapping[];
}

export interface CatalogIndexItem {
  name: string;
  schema_name: string | null;
  table_name: string;
  unique: boolean | null;
  columns: string[];
  method: string | null;
}

export interface CatalogCategoryAssignment {
  schema_name: string | null;
  table_name: string;
  provenance: string | null;
  is_primary: boolean | null;
  confidence: number | string | null;
  note: string | null;
}

export interface CatalogCategoryItem {
  id: string;
  name: string | null;
  description: string | null;
  assignments: CatalogCategoryAssignment[];
}

export type CatalogTableListResponse = CatalogQueryEnvelope<CatalogTableItem>;
export type CatalogColumnListResponse = CatalogQueryEnvelope<CatalogColumnItem>;
export type CatalogRelationListResponse = CatalogQueryEnvelope<CatalogRelationItem>;
export type CatalogIndexListResponse = CatalogQueryEnvelope<CatalogIndexItem>;
export type CatalogCategoryListResponse = CatalogQueryEnvelope<CatalogCategoryItem>;

export interface ApiErrorBody {
  code?: string;
  message?: string;
  path?: string | null;
}

export class CatalogApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(status: number, message: string, code: string | null = null) {
    super(message);
    this.name = "CatalogApiError";
    this.status = status;
    this.code = code;
  }
}

export type RelationDirection = "OUT" | "IN";

export interface DirectedRelation {
  direction: RelationDirection;
  key: string;
  name: string | null;
  sourceSchema: string | null;
  sourceTable: string;
  targetSchema: string | null;
  targetTable: string;
  columns: CatalogRelationColumnMapping[];
}
