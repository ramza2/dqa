import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { OfflineMetadataSummaryPanel } from "../components/OfflineMetadataSummaryPanel";
import { compareOfflineSummary, parseOfflineMetadataSummary } from "../utils/offlineMetadataSummary";
import type { SnapshotSummary, SnapshotReviewPreview } from "../types/schemaSnapshot";
const fingerprint = "a".repeat(64);
const row: SnapshotSummary = {
  id: 7, source_name: "oracle_demis_mock", db_type: "oracle",
  database_name: "FREEPDB1", schema_name: "DEMIS_OWNER",
  schema_fingerprint: fingerprint, previous_revision_id: null,
  captured_by: "test", captured_at: "2026-10-27T00:00:00Z",
  counts: { tables: 2, columns: 5 }, diff_status: "NO_BASELINE", total_changes: null,
};
const preview: SnapshotReviewPreview = {
  source_name: row.source_name, revision_id: 7, latest_revision_id: 7,
  is_latest: true, schema_fingerprint: fingerprint, captured_at: row.captured_at,
  review_status: "REVIEW_REQUIRED", diff_status: "NO_BASELINE",
  identical: null, total_changes: null, snapshot_verified: true,
  candidate_package_valid: true, candidate_package_readiness: "WARNING",
  preflight_status: "NOT_VERIFIED", activation_eligible: false,
  required_gates: ["MANUAL_CHANGE_REVIEW", "INDEPENDENT_PREFLIGHT",
    "EXPLICIT_CATALOG_IMPORT", "READY_ELIGIBILITY_VERIFICATION", "MANUAL_ACTIVATION"],
};
const valid = {
  format: "dqa-offline-metadata-summary-v1", source_name: "oracle_demis_mock",
  schema_fingerprint: fingerprint, table_count: 2, column_count: 5,
  claim_binding: "MATCHED_UNTRUSTED", review_draft_status: "ACKNOWLEDGED_UNVERIFIED",
  issuer_authenticated: false, review_actor_authenticated: false,
  independent_preflight_verified: false, site_approval_verified: false,
  catalog_package_readiness: "WARNING", catalog_ready: false,
  activation_eligible: false,
};
afterEach(() => vi.unstubAllGlobals());

describe("M2-1H local offline summary", () => {
  it("accepts only strict unapproved summary and refuses arbitrary data", () => {
    expect(parseOfflineMetadataSummary(JSON.stringify(valid))).not.toBeNull();
    for (const bad of [
      { ...valid, catalog_ready: true }, { ...valid, activation_eligible: true },
      { ...valid, catalog_package_readiness: "READY" },
      { ...valid, approved: true }, { ...valid, patient_rows: [] },
      { ...valid, issuer_authenticated: true },
      { ...valid, source_name: "real_demis" }, { ...valid, schema_fingerprint: "x" },
      { ...valid, claim_binding: "ABSENT" },
      { ...valid, table_count: 2.4 }, { ...valid, review_draft_status: "APPROVED" },
    ]) expect(parseOfflineMetadataSummary(JSON.stringify(bad))).toBeNull();
    expect(parseOfflineMetadataSummary("{bad json")).toBeNull();
    expect(parseOfflineMetadataSummary("x".repeat(2049))).toBeNull();
  });
  it("distinguishes latest match, mismatch, stale, and scope failure", () => {
    const report = parseOfflineMetadataSummary(JSON.stringify(valid));
    expect(report).not.toBeNull();
    if (!report) return;
    expect(compareOfflineSummary(report, row, preview)).toBe("FINGERPRINT_MATCH_UNTRUSTED");
    expect(compareOfflineSummary(report, row, null)).toBe("SNAPSHOT_PREVIEW_UNAVAILABLE");
    expect(compareOfflineSummary(report, { ...row, schema_fingerprint: "b".repeat(64) },
      { ...preview, schema_fingerprint: "b".repeat(64) })).toBe("FINGERPRINT_DIFFERENCE_UNTRUSTED");
    expect(compareOfflineSummary(report, { ...row, counts: { tables: 1, columns: 5 } }, preview))
      .toBe("COUNT_CONFLICT_UNTRUSTED");
    expect(compareOfflineSummary(report, row, { ...preview, is_latest: false,
      latest_revision_id: 8, review_status: "SUPERSEDED" })).toBe("SUPERSEDED");
    expect(compareOfflineSummary(report, { ...row, source_name: "other" },
      { ...preview, source_name: "other" })).toBe("OUT_OF_SCOPE");
  });
  it("shows local advisory only; never sends text to a backend", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);
    const user = userEvent.setup();
    render(<OfflineMetadataSummaryPanel snapshot={row} preview={preview} />);
    fireEvent.change(screen.getByRole("textbox", { name: "오프라인 검증 요약 JSON" }), { target: { value: JSON.stringify(valid) } });
    await user.click(screen.getByRole("button", { name: "요약 로컬 대조" }));
    const result = await screen.findByTestId("offline-summary-result");
    expect(result).toHaveTextContent("FINGERPRINT_MATCH_UNTRUSTED");
    expect(result).toHaveTextContent("ACKNOWLEDGED_UNVERIFIED");
    expect(result).toHaveTextContent("NOT_VERIFIED");
    expect(result).toHaveTextContent("WARNING / false");
    expect(fetchSpy).not.toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "요약 지우기" }));
    expect(screen.queryByTestId("offline-summary-result")).not.toBeInTheDocument();
  });
  it("rejects hostile input without echoing it", async () => {
    const user = userEvent.setup();
    render(<OfflineMetadataSummaryPanel snapshot={row} preview={preview} />);
    fireEvent.change(screen.getByRole("textbox", { name: "오프라인 검증 요약 JSON" }), { target: { value: '{"patient":"PRIVATE_NAME"}' } });
    await user.click(screen.getByRole("button", { name: "요약 로컬 대조" }));
    expect(await screen.findByTestId("offline-summary-invalid")).toHaveTextContent("원문은 표시하지 않습니다");
    expect(screen.queryByTestId("offline-summary-result")).not.toBeInTheDocument();
  });
});
