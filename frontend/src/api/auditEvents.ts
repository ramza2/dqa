import { apiGet } from "./client";
import type { QueryAuditEventBundleResponse } from "../types/auditEvents";

/** Requires AUDIT_READ. Callers must treat 403 as history-only denial. */
export function getAuditEventsById(auditId: string): Promise<QueryAuditEventBundleResponse> {
  const trimmed = auditId.trim();
  return apiGet<QueryAuditEventBundleResponse>(
    `/audit-events/${encodeURIComponent(trimmed)}`,
  );
}
