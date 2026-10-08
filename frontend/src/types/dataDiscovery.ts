/** Types mirrored from backend Pydantic Data Discovery contracts (Phase 27-C). */

export type DataDiscoverySearchMode = "keyword" | "semantic" | "hybrid";
export type DiscoveryObjectType = "TABLE" | "COLUMN";
export type DocumentState = "READY" | "NOT_READY";
export type EmbeddingState =
  | "NOT_CONFIGURED"
  | "CONFIGURATION_ERROR"
  | "NOT_READY"
  | "READY";

export interface PhysicalDiscoveryIdentity {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  schema_name: string;
  table_name: string;
  column_name: string | null;
}

export interface DataDiscoverySearchRequest {
  source_name: string;
  query: string;
  mode: DataDiscoverySearchMode;
  object_type?: DiscoveryObjectType | null;
  top_k?: number;
  expand_terms?: boolean;
  expand_relations?: boolean;
  max_relation_hops?: number;
}

export interface DataDiscoverySearchResultItem {
  rank: number;
  identity: PhysicalDiscoveryIdentity;
  document_key: string;
  object_type: DiscoveryObjectType;
  keyword_score: number | null;
  keyword_rank: number | null;
  semantic_score: number | null;
  semantic_rank: number | null;
  rrf_score: number | null;
  evidence: string[];
  evidence_snippet: string | null;
}

export interface DataDiscoveryRelationHop {
  from_schema: string;
  from_table: string;
  to_schema: string;
  to_table: string;
  constraint_name: string | null;
  direction: "outbound" | "inbound";
  from_columns: string[];
  to_columns: string[];
}

export interface DataDiscoveryRelatedTable {
  schema_name: string;
  table_name: string;
  hop_distance: number;
  seed_schema: string;
  seed_table: string;
  path: DataDiscoveryRelationHop[];
}

export interface DataDiscoverySearchTimings {
  keyword_ms: number;
  semantic_ms: number;
  total_ms: number;
}

export interface DataDiscoverySearchResponse {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  mode: DataDiscoverySearchMode;
  model_key: string | null;
  original_query: string;
  normalized_query: string;
  expanded_query: string;
  matched_concepts: string[];
  expanded_terms: string[];
  results: DataDiscoverySearchResultItem[];
  related_tables: DataDiscoveryRelatedTable[];
  timings: DataDiscoverySearchTimings;
}

export interface DataDiscoveryEmbeddingCoverage {
  document_count: number;
  embedding_count: number;
  current_count: number;
  stale_count: number;
  missing_count: number;
}

export interface DataDiscoveryIndexStatusResponse {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  document_count: number;
  document_state: DocumentState;
  embedding_state: EmbeddingState;
  provider: string | null;
  model_name: string | null;
  model_revision: string | null;
  model_key: string | null;
  dimension: number | null;
  normalized: boolean | null;
  coverage: DataDiscoveryEmbeddingCoverage | null;
  embedding_error_code: string | null;
}

export interface DataDiscoveryRebuildResponse {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  document_count: number;
  upserted_count: number;
  deleted_count: number;
  builder_version: string;
}

export interface DataDiscoveryEmbeddingSyncResponse {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  model_key: string;
  document_count: number;
  embedded_count: number;
  skipped_count: number;
  coverage: DataDiscoveryEmbeddingCoverage;
}
