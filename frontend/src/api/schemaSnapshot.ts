import { apiGet } from "./client";
import type {
  SnapshotDetail,
  SnapshotReviewEvent,
  SnapshotReviewPreview,
  SnapshotSummary,
} from "../types/schemaSnapshot";

const base = "/schema-inspector/snapshots";

export function listSnapshotHistory(
  sourceName: string, offset = 0, limit = 50, init?: RequestInit,
): Promise<SnapshotSummary[]> {
  return apiGet<SnapshotSummary[]>(base, {
    source_name: sourceName, offset, limit,
  }, init);
}

export function getSnapshotHistoryDetail(
  sourceName: string, revisionId: number, init?: RequestInit,
): Promise<SnapshotDetail> {
  return apiGet<SnapshotDetail>(`${base}/${revisionId}`, { source_name: sourceName }, init);
}

export function getSnapshotReviewPreview(
  sourceName: string, revisionId: number, init?: RequestInit,
): Promise<SnapshotReviewPreview> {
  return apiGet<SnapshotReviewPreview>(
    `${base}/${revisionId}/review`, { source_name: sourceName }, init,
  );
}

export function listSnapshotReviewEvents(
  sourceName: string, revisionId: number, init?: RequestInit,
): Promise<SnapshotReviewEvent[]> {
  return apiGet<SnapshotReviewEvent[]>(
    `${base}/${revisionId}/reviews`, { source_name: sourceName }, init,
  );
}
