/** Types mirrored from backend GET /api/v1/audit-events/{audit_id}. */

export type AuditEventType = "QUERY_REQUEST" | "QUERY_EXECUTION";
export type AuditStatus = "STARTED" | "SUCCEEDED" | "FAILED" | "DENIED";
export type ParameterLoggingPolicy = "NAMES_ONLY";

export interface QueryAuditEventView {
  id: number;
  audit_id: string;
  event_type: AuditEventType;
  status: AuditStatus;
  actor_id: string | null;
  source_name: string | null;
  catalog_revision_id: number | null;
  catalog_fingerprint: string | null;
  template_id: number | null;
  template_version_id: number | null;
  connection_profile_id: number | null;
  parameter_names: string[];
  sensitive_parameter_names: string[];
  parameter_logging_policy: ParameterLoggingPolicy;
  failure_category: string | null;
  elapsed_ms: number | null;
  row_count: number | null;
  result_truncated: boolean | null;
  created_at: string;
}

export interface QueryAuditEventBundleResponse {
  audit_id: string;
  items: QueryAuditEventView[];
}
