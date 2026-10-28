/** Projections of existing Query Template review / authoring APIs. */
export type TemplateApprovalStatus = "DRAFT" | "IN_REVIEW" | "APPROVED" | "REJECTED";

export interface TemplateCompatibility {
  mode: "EXACT_FINGERPRINT";
  compatible: boolean;
  pinned_revision_id: number;
  pinned_schema_fingerprint: string;
  current_revision_id: number | null;
  current_schema_fingerprint: string | null;
}

export interface TemplateParameterSchema {
  name: string;
  type: string;
  required: boolean;
  sensitive: boolean;
  label?: string | null;
  description?: string | null;
  default?: unknown;
  allowed_values?: unknown[] | null;
  pattern?: string | null;
  min?: number | null;
  max?: number | null;
  min_items?: number | null;
  max_items?: number | null;
}

export interface ReviewTemplateSummary {
  id: number;
  stable_key: string;
  name: string;
  description: string | null;
  source_name: string;
  target_schemas: string[];
  enabled: boolean;
  current_version_id: number | null;
  current_version: number | null;
  approval_status: TemplateApprovalStatus | null;
  compatibility: TemplateCompatibility | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewTemplateList {
  total: number;
  limit: number;
  offset: number;
  items: ReviewTemplateSummary[];
}

export interface ReviewTemplateDetail extends ReviewTemplateSummary {
  version: {
    id: number;
    version: number;
    sql_text: string;
    parameter_schema: TemplateParameterSchema[];
    row_limit: number;
    timeout_seconds: number;
    approval_status: TemplateApprovalStatus;
    compatibility: TemplateCompatibility;
    created_by: string | null;
    created_at: string;
    approved_by: string | null;
    approved_at: string | null;
    approval_note: string | null;
  };
}

export interface TemplateSqlSafetyReview {
  template_id: number;
  version_id: number;
  version: number;
  safe: boolean;
  statement_count: number;
  referenced_parameters: string[];
  declared_parameters: string[];
  issues: { code: string; message: string }[];
}

export interface TemplateReviewEvent {
  id: number;
  template_id: number;
  version_id: number;
  from_status: TemplateApprovalStatus;
  to_status: TemplateApprovalStatus;
  actor: string | null;
  note: string | null;
  created_at: string;
}

export interface TemplateReviewEventList {
  items: TemplateReviewEvent[];
}

export interface TemplateCreateRequest {
  stable_key: string;
  name: string;
  description?: string | null;
  source_name: string;
  target_schemas: string[];
  sql_text: string;
  parameter_schema: TemplateParameterSchema[];
  row_limit: number;
  timeout_seconds: number;
}

export interface TemplateUpdateRequest {
  name?: string;
  description?: string | null;
  target_schemas?: string[];
  sql_text?: string;
  parameter_schema?: TemplateParameterSchema[];
  row_limit?: number;
  timeout_seconds?: number;
}

export interface TemplateNewVersionRequest {
  sql_text?: string;
  parameter_schema?: TemplateParameterSchema[];
  row_limit?: number;
  timeout_seconds?: number;
}
