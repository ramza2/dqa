/** S-05-D: verify a read-only Snapshot preview contract before showing gate guidance.
 * This is not a preflight verifier and cannot authorize Catalog operations. */
import type { SnapshotReviewPreview } from "../types/schemaSnapshot";

export const SNAPSHOT_REVIEW_REQUIRED_GATES = [
  "MANUAL_CHANGE_REVIEW",
  "INDEPENDENT_PREFLIGHT",
  "EXPLICIT_CATALOG_IMPORT",
  "READY_ELIGIBILITY_VERIFICATION",
  "MANUAL_ACTIVATION",
] as const;

export const SNAPSHOT_REVIEW_GATE_LABELS: Record<(typeof SNAPSHOT_REVIEW_REQUIRED_GATES)[number], string> = {
  MANUAL_CHANGE_REVIEW: "변경 내용의 수동 검토",
  INDEPENDENT_PREFLIGHT: "독립 DBA·보안 Preflight 증빙",
  EXPLICIT_CATALOG_IMPORT: "Catalog Package v2 명시적 Import",
  READY_ELIGIBILITY_VERIFICATION: "READY 적격성 별도 검증",
  MANUAL_ACTIVATION: "적격 Catalog Revision 수동 활성화",
};

/** Treat even typed HTTP payloads as untrusted. Fail closed on unexpected gate
 * vocabulary, promoted approval flags, stale revision flags, or malformed lists. */
export function isSafeSnapshotReviewPreview(value: unknown): value is SnapshotReviewPreview {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const preview = value as Partial<SnapshotReviewPreview>;
  const revisionId = preview.revision_id;
  const latestRevisionId = preview.latest_revision_id;
  const gates: unknown = preview.required_gates;
  return preview.preflight_status === "NOT_VERIFIED"
    && preview.candidate_package_readiness === "WARNING"
    && preview.activation_eligible === false
    && preview.snapshot_verified === true
    && preview.candidate_package_valid === true
    && typeof revisionId === "number"
    && Number.isSafeInteger(revisionId)
    && revisionId > 0
    && typeof latestRevisionId === "number"
    && Number.isSafeInteger(latestRevisionId)
    && latestRevisionId >= revisionId
    && preview.is_latest === (latestRevisionId === revisionId)
    && preview.review_status === (preview.is_latest ? "REVIEW_REQUIRED" : "SUPERSEDED")
    && Array.isArray(gates)
    && gates.length === SNAPSHOT_REVIEW_REQUIRED_GATES.length
    && SNAPSHOT_REVIEW_REQUIRED_GATES.every((gate) => gates.includes(gate));
}
