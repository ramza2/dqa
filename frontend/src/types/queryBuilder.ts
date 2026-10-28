/** Preview-only physical Catalog query builder — not approval/execute. */
export type CatalogPreviewOperator =
  | "EQ" | "NE" | "LT" | "LE" | "GT" | "GE" | "LIKE"
  | "IS_NULL" | "IS_NOT_NULL";

export interface CatalogPreviewPredicate {
  column: string;
  operator: CatalogPreviewOperator;
}

export interface CatalogPreviewRequest {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  schema_name: string;
  table_name: string;
  columns: string[];
  predicates: CatalogPreviewPredicate[];
  row_limit: number;
}

export interface CatalogPreviewResponse {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  sql_text: string;
  parameters: { name: string; column: string | null; type: string }[];
  preview_only: true;
  approved: false;
  executable: false;
  template_id: null;
}
