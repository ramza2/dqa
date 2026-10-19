import type { SnapshotReviewEvent } from "../types/schemaSnapshot";

/** The backend returns at most 100 newest events, sorted by id descending.
 * This checks only the returned list; it is not an independent audit or DBA approval.
 */
const MAX_EVENTS = 100;

export function isSafeSnapshotReviewEvents(
  payload: unknown,
  scope: { sourceName: string; revisionId: number; schemaFingerprint: string },
): payload is SnapshotReviewEvent[] {
  if (!Array.isArray(payload) || payload.length > MAX_EVENTS) return false;

  for (let i = 0; i < payload.length; i += 1) {
    const entry: unknown = payload[i];
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) return false;
    const event = entry as Partial<SnapshotReviewEvent>;
    // Backend GET omits these fields. Inspect raw JSON values, not the
    // compile-time false-only type, so injected approval claims fail closed.
    const raw = entry as Record<string, unknown>;
    const id = event.id;
    const predecessor = event.previous_review_event_id;
    if (
      typeof id !== "number" || !Number.isSafeInteger(id) || id <= 0
      || event.source_name !== scope.sourceName
      || event.snapshot_revision_id !== scope.revisionId
      || event.schema_fingerprint !== scope.schemaFingerprint
      || (predecessor !== null
        && (typeof predecessor !== "number" || !Number.isSafeInteger(predecessor)
          || predecessor <= 0 || predecessor >= id))
      || typeof event.reviewed_by !== "string"
      || !event.reviewed_by.trim()
      || event.reviewed_by !== event.reviewed_by.trim()
      || event.reviewed_by.length > 255
      || typeof event.reviewed_at !== "string"
      || !Number.isFinite(Date.parse(event.reviewed_at))
      || !(
        (event.decision === "ACKNOWLEDGED" && event.reason_code === "REVIEWED_CHANGES")
        || (event.decision === "CHANGES_REQUESTED"
          && (event.reason_code === "RECHECK_REQUIRED" || event.reason_code === "SCOPE_UNCLEAR"))
      )
      || (raw.independent_preflight_verified !== undefined && raw.independent_preflight_verified !== false)
      || (raw.catalog_ready !== undefined && raw.catalog_ready !== false)
      || (raw.catalog_activated !== undefined && raw.catalog_activated !== false)
    ) return false;

    // The previous link must identify the next returned row. Global ID gaps
    // are normal (other sources), but a broken per-revision chain is not.
    if (i + 1 < payload.length) {
      const next: unknown = payload[i + 1];
      if (!next || typeof next !== "object" || Array.isArray(next)) return false;
      if (predecessor !== (next as Partial<SnapshotReviewEvent>).id) return false;
    } else if (payload.length < MAX_EVENTS && predecessor !== null) {
      // A short list must reach the first event. A 100-row limit can truncate.
      return false;
    }
  }
  return true;
}
