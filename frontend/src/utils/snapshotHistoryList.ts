import type { SnapshotSummary } from "../types/schemaSnapshot";

/** List GET is newest first and Source scoped. Keep this strictly display-only.
 * It is not a Snapshot verification, independent DBA preflight or activation.
 */
const MAX_PAGE_SIZE = 50;
const FINGERPRINT = /^[0-9a-f]{64}$/;

export function isSafeSnapshotHistoryList(
  payload: unknown, sourceName: string, limit = MAX_PAGE_SIZE,
): payload is SnapshotSummary[] {
  if (!Array.isArray(payload) || payload.length > limit
    || !Number.isSafeInteger(limit) || limit < 1 || limit > MAX_PAGE_SIZE) return false;

  for (let i = 0; i < payload.length; i += 1) {
    const raw: unknown = payload[i];
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return false;
    const row = raw as Partial<SnapshotSummary>;
    const previous = row.previous_revision_id;
    if (
      typeof row.id !== "number" || !Number.isSafeInteger(row.id) || row.id <= 0
      || row.source_name !== sourceName
      || typeof row.db_type !== "string" || !row.db_type.trim()
      || typeof row.database_name !== "string" || !row.database_name.trim()
      || typeof row.schema_name !== "string" || !row.schema_name.trim()
      || typeof row.schema_fingerprint !== "string"
      || !FINGERPRINT.test(row.schema_fingerprint)
      || (previous !== null && (typeof previous !== "number"
        || !Number.isSafeInteger(previous) || previous <= 0 || previous >= row.id))
      || typeof row.captured_by !== "string" || !row.captured_by.trim()
      || typeof row.captured_at !== "string" || !Number.isFinite(Date.parse(row.captured_at))
      || !row.counts || typeof row.counts !== "object" || Array.isArray(row.counts)
    ) return false;

    const counts = Object.values(row.counts);
    if (counts.some((n) => typeof n !== "number" || !Number.isSafeInteger(n) || n < 0)) {
      return false;
    }

    if (row.diff_status === "NO_BASELINE") {
      if (previous !== null || row.total_changes !== null) return false;
    } else if (row.diff_status === "COMPARED") {
      if (previous === null || typeof row.total_changes !== "number"
        || !Number.isSafeInteger(row.total_changes) || row.total_changes < 0) return false;
    } else {
      return false;
    }

    // Append-only, Source-filtered backend list uses id DESC. A row's
    // predecessor must be the next item on this page; the final one can
    // point outside the page due to pagination.
    if (i + 1 < payload.length) {
      const next: unknown = payload[i + 1];
      if (!next || typeof next !== "object" || Array.isArray(next)) return false;
      const nextId = (next as Partial<SnapshotSummary>).id;
      if (previous !== nextId) return false;
    }
  }
  return true;
}
