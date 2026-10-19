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

/** Immutable Catalog Package import metadata; not a Snapshot or activation event. */
export interface CatalogImportRevisionSummary {
  id: number;
  source_name: string;
  db_type: string;
  database_name: string | null;
  default_schema: string | null;
  package_format: string;
  package_version: string;
  package_readiness: PackageReadiness;
  activation_eligible: boolean;
  schema_fingerprint: string;
  archive_sha256: string;
  manifest_sha256: string;
  validation_status: string;
  generated_at: string;
  imported_at: string;
  table_count: number;
  column_count: number;
  relation_count: number;
  index_count: number;
  category_count: number;
  category_assignment_count: number;
  managed_file_count: number;
}

/** Append-only active Catalog pointer history; NOT Snapshot revision history. */
export interface CatalogActivationEventSummary {
  source_name: string;
  previous_revision_id: number | null;
  activated_revision_id: number;
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
