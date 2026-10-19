/** Public, safe Snapshot history contracts from schema_snapshot_history.py.
 * No raw Snapshot JSON, credentials, Oracle defaults, or SQL bodies. */
export type SnapshotDiffStatus = "NO_BASELINE" | "COMPARED";

export interface SnapshotSummary {
  id: number;
  source_name: string;
  db_type: string;
  database_name: string;
  schema_name: string;
  schema_fingerprint: string;
  previous_revision_id: number | null;
  captured_by: string;
  captured_at: string;
  counts: Record<string, number>;
  diff_status: SnapshotDiffStatus;
  total_changes: number | null;
}

export interface SnapshotChange {
  object_type: string;
  change_type: string;
  object_key: string[];
  changed_fields: string[];
}

export interface SnapshotDetail extends SnapshotSummary {
  diff_counts: Record<string, { added: number; removed: number; changed: number }>;
  changes: SnapshotChange[];
}

export interface SnapshotReviewPreview {
  source_name: string;
  revision_id: number;
  latest_revision_id: number;
  is_latest: boolean;
  schema_fingerprint: string;
  captured_at: string;
  review_status: "REVIEW_REQUIRED" | "SUPERSEDED";
  diff_status: SnapshotDiffStatus;
  identical: boolean | null;
  total_changes: number | null;
  snapshot_verified: boolean;
  candidate_package_valid: boolean;
  candidate_package_readiness: "WARNING";
  preflight_status: "NOT_VERIFIED";
  activation_eligible: false;
  required_gates: string[];
}

export interface SnapshotReviewEvent {
  id: number;
  source_name: string;
  snapshot_revision_id: number;
  schema_fingerprint: string;
  previous_review_event_id: number | null;
  decision: "ACKNOWLEDGED" | "CHANGES_REQUESTED";
  reason_code: "REVIEWED_CHANGES" | "RECHECK_REQUIRED" | "SCOPE_UNCLEAR";
  reviewed_by: string;
  reviewed_at: string;
  /** Older synthetic fixtures may include these; the live GET route omits them. */
  independent_preflight_verified?: false;
  catalog_ready?: false;
  catalog_activated?: false;
}
