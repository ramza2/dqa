import { apiGet, apiPost } from "./client";

const root = (profileId: number) => `/schema-inspector/mock-targets/${profileId}`;

export interface MockInspectorReadiness {
  profile_id: number;
  ready: boolean;
  reason_code: string;
  schema_name: string | null;
  live_connection_tested: false;
  site_approved: false;
  catalog_activated: false;
}

export interface MockInspectionSummary {
  status: string;
  source_name: string;
  schema_name: string;
  table_count: number;
  column_count: number;
  primary_key_column_count: number;
  unique_key_column_count: number;
  foreign_key_count: number;
  index_count: number;
  imported: false;
  activated: false;
}

export interface MockSnapshotSummary {
  id: number;
  source_name: string;
  schema_name: string;
  schema_fingerprint: string;
  diff_status: "NO_BASELINE" | "COMPARED";
  created: boolean;
  imported: false;
  activated: false;
}

interface SnapshotRevision {
  id: number;
  source_name: string;
}

/** Purely config-based; server guards physical identity and separate credentials. */
export function checkMockInspectorReadiness(profileId: number): Promise<MockInspectorReadiness> {
  return apiGet<MockInspectorReadiness>(`${root(profileId)}/readiness`);
}

/** Metadata-only Oracle ALL_* scan. No Catalog changes. */
export function inspectSelectedMock(profileId: number): Promise<MockInspectionSummary> {
  return apiPost<Record<string, never>, MockInspectionSummary>(
    `${root(profileId)}/inspect`, {},
  );
}

/** Existing history is authoritative for the optimistic CAS predecessor. */
export async function captureSelectedMock(profileId: number): Promise<MockSnapshotSummary> {
  const previous = await apiGet<SnapshotRevision[]>("/schema-inspector/snapshots", {
    source_name: "oracle_demis_mock", limit: 1,
  });
  if (!Array.isArray(previous) ||
      (previous.length > 0 && (previous[0].source_name !== "oracle_demis_mock" ||
       !Number.isSafeInteger(previous[0].id) || previous[0].id <= 0))) {
    throw new Error("invalid Snapshot predecessor");
  }
  return apiPost<
    { capture_request_id: string; expected_previous_revision_id: number | null },
    MockSnapshotSummary
  >(`${root(profileId)}/snapshots/capture`, {
    capture_request_id: window.crypto.randomUUID(),
    expected_previous_revision_id: previous[0]?.id ?? null,
  });
}
