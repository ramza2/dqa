/** M2-1H: local UI advisory based on an untrusted, metadata-only CLI summary. */
import type { SnapshotSummary, SnapshotReviewPreview } from "../types/schemaSnapshot";
import { isSafeSnapshotReviewPreview } from "./snapshotReviewGates";

export const OFFLINE_SUMMARY_LIMIT = 2048;
export interface OfflineMetadataSummary {
  format: "dqa-offline-metadata-summary-v1";
  source_name: "oracle_demis_mock";
  schema_fingerprint: string;
  table_count: number;
  column_count: number;
  claim_binding: "ABSENT" | "MATCHED_UNTRUSTED";
  review_draft_status: "ABSENT" | "ACKNOWLEDGED_UNVERIFIED" | "CHANGES_REQUESTED_UNVERIFIED";
  issuer_authenticated: false;
  review_actor_authenticated: false;
  independent_preflight_verified: false;
  site_approval_verified: false;
  catalog_package_readiness: "WARNING";
  catalog_ready: false;
  activation_eligible: false;
}
const KEYS = [
  "format", "source_name", "schema_fingerprint", "table_count", "column_count",
  "claim_binding", "review_draft_status", "issuer_authenticated",
  "review_actor_authenticated", "independent_preflight_verified",
  "site_approval_verified", "catalog_package_readiness", "catalog_ready",
  "activation_eligible",
];
const HAS = (object: Record<string, unknown>, key: string) =>
  Object.prototype.hasOwnProperty.call(object, key);

export function parseOfflineMetadataSummary(raw: string): OfflineMetadataSummary | null {
  if (raw.length === 0 || raw.length > OFFLINE_SUMMARY_LIMIT) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    const item = value as Record<string, unknown>;
    if (Object.keys(item).length !== KEYS.length || !KEYS.every((k) => HAS(item, k))) return null;
    if (item.format !== "dqa-offline-metadata-summary-v1" || item.source_name !== "oracle_demis_mock"
      || typeof item.schema_fingerprint !== "string" || !/^[a-f0-9]{64}$/.test(item.schema_fingerprint)
      || typeof item.table_count !== "number" || !Number.isSafeInteger(item.table_count)
      || item.table_count < 1 || item.table_count > 20000
      || typeof item.column_count !== "number" || !Number.isSafeInteger(item.column_count)
      || item.column_count < 1 || item.column_count > 20000) return null;
    if (item.claim_binding !== "ABSENT" && item.claim_binding !== "MATCHED_UNTRUSTED") return null;
    if (!["ABSENT", "ACKNOWLEDGED_UNVERIFIED", "CHANGES_REQUESTED_UNVERIFIED"].includes(String(item.review_draft_status))
      || (item.review_draft_status !== "ABSENT" && item.claim_binding !== "MATCHED_UNTRUSTED")) return null;
    if (item.issuer_authenticated !== false || item.review_actor_authenticated !== false
      || item.independent_preflight_verified !== false || item.site_approval_verified !== false
      || item.catalog_package_readiness !== "WARNING" || item.catalog_ready !== false
      || item.activation_eligible !== false) return null;
    return item as unknown as OfflineMetadataSummary;
  } catch { return null; }
}

export type LocalSummaryStatus =
  "SNAPSHOT_PREVIEW_UNAVAILABLE" | "OUT_OF_SCOPE" | "SUPERSEDED" |
  "FINGERPRINT_MATCH_UNTRUSTED" | "FINGERPRINT_DIFFERENCE_UNTRUSTED" |
  "COUNT_CONFLICT_UNTRUSTED";

export function compareOfflineSummary(
  summary: OfflineMetadataSummary, row: SnapshotSummary, preview: SnapshotReviewPreview | null,
): LocalSummaryStatus {
  if (!preview || !isSafeSnapshotReviewPreview(preview)
    || preview.source_name !== row.source_name || preview.revision_id !== row.id
    || preview.schema_fingerprint !== row.schema_fingerprint) return "SNAPSHOT_PREVIEW_UNAVAILABLE";
  if (row.source_name !== summary.source_name || row.db_type !== "oracle"
    || row.database_name !== "FREEPDB1" || row.schema_name !== "DEMIS_OWNER") return "OUT_OF_SCOPE";
  if (!preview.is_latest) return "SUPERSEDED";
  if (summary.schema_fingerprint !== row.schema_fingerprint) return "FINGERPRINT_DIFFERENCE_UNTRUSTED";
  if (row.counts.tables !== summary.table_count || row.counts.columns !== summary.column_count)
    return "COUNT_CONFLICT_UNTRUSTED";
  return "FINGERPRINT_MATCH_UNTRUSTED";
}
