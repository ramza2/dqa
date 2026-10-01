/** Types mirrored from backend Query Assistant / execution contracts. */

export type ExecutionFormBlockerCode =
  | "DEMIS_ADAPTER_UNAVAILABLE"
  | "CONNECTION_PROFILE_INCOMPLETE";

export type ExecutionBlockerCode = "DEMIS_ADAPTER_UNAVAILABLE";

export type ParameterType =
  | "string"
  | "integer"
  | "decimal"
  | "boolean"
  | "date"
  | "datetime"
  | "enum"
  | "string_list"
  | "integer_list"
  | string;

export interface TemplateRecommendationRequest {
  source_name: string;
  request_text: string;
}

export interface RecommendedTemplate {
  template_id: number;
  version_id: number;
  version: number;
  stable_key: string;
  name: string;
  description: string | null;
  target_schemas: string[];
  parameter_names: string[];
  parameter_count: number;
}

export interface TemplateRecommendationResponse {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  needs_clarification: boolean;
  clarification_question: string | null;
  /** Template routing confidence only — not clinical confidence. */
  confidence: number | null;
  reason: string | null;
  recommended_template: RecommendedTemplate | null;
  ranked_candidates: RecommendedTemplate[];
}

export interface ExecutionFormParameter {
  name: string;
  label: string | null;
  description: string | null;
  type: ParameterType;
  required: boolean;
  default: unknown;
  allowed_values: unknown[] | null;
  pattern: string | null;
  min: number | null;
  max: number | null;
  min_items: number | null;
  max_items: number | null;
  sensitive: boolean;
}

export interface ExecutionFormTemplate {
  template_id: number;
  version_id: number;
  version: number;
  stable_key: string;
  name: string;
  description: string | null;
}

export interface ExecutionFormEnvironment {
  environment: string;
  execution_available: boolean;
  execution_blockers: ExecutionFormBlockerCode[];
}

export interface ExecutionFormResponse {
  source_name: string;
  catalog_revision_id: number;
  catalog_fingerprint: string;
  template: ExecutionFormTemplate;
  parameters: ExecutionFormParameter[];
  environments: ExecutionFormEnvironment[];
}

export interface ParameterExtractionRequest {
  source_name: string;
  template_id: number;
  version_id: number;
  request_text: string;
}

export interface ParameterExtractionIssueView {
  parameter_name: string;
  code: string;
  message: string;
}

export interface ParameterExtractionResponse {
  source_name: string;
  catalog_revision_id: number;
  schema_fingerprint: string;
  template_id: number;
  version_id: number;
  version: number;
  needs_clarification: boolean;
  clarification_question: string | null;
  resolved_parameters: Record<string, unknown>;
  issues: ParameterExtractionIssueView[];
  sensitive_parameter_names: string[];
}

export interface ExecutionPreviewRequest {
  source_name: string;
  environment: string;
  template_id: number;
  version_id: number;
  parameters: Record<string, unknown>;
}

export interface ExecutionPreviewResponse {
  source_name: string;
  environment: string;
  catalog_revision_id: number;
  catalog_fingerprint: string;
  template_id: number;
  version_id: number;
  version: number;
  connection_profile_id: number;
  resolved_parameters: Record<string, unknown>;
  sensitive_parameter_names: string[];
  row_limit: number;
  timeout_seconds: number;
  execution_available: boolean;
  execution_blockers: ExecutionBlockerCode[];
}

export type QueryExecutionRequest = ExecutionPreviewRequest;

export interface QueryExecutionResponse {
  audit_id: string;
  source_name: string;
  environment: string;
  catalog_revision_id: number;
  catalog_fingerprint: string;
  template_id: number;
  version_id: number;
  version: number;
  connection_profile_id: number;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
  truncated: boolean;
  elapsed_ms: number;
}
