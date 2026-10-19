import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SnapshotReviewGates } from "../components/SnapshotReviewGates";
import {
  isSafeSnapshotReviewPreview, SNAPSHOT_REVIEW_REQUIRED_GATES,
} from "../utils/snapshotReviewGates";
import type { SnapshotReviewPreview } from "../types/schemaSnapshot";

const base: SnapshotReviewPreview = {
  source_name: "synthetic_source", revision_id: 10, latest_revision_id: 10,
  is_latest: true, schema_fingerprint: "a".repeat(64),
  captured_at: "2026-10-16T00:00:00Z", review_status: "REVIEW_REQUIRED",
  diff_status: "COMPARED", identical: false, total_changes: 1,
  snapshot_verified: true, candidate_package_valid: true,
  candidate_package_readiness: "WARNING", preflight_status: "NOT_VERIFIED",
  activation_eligible: false, required_gates: [...SNAPSHOT_REVIEW_REQUIRED_GATES],
};

describe("S-05-D Snapshot review gates (advisory only)", () => {
  it("shows the five existing required gates without conveying approval or actions", () => {
    expect(isSafeSnapshotReviewPreview(base)).toBe(true);
    render(<SnapshotReviewGates preview={base} />);
    const panel = screen.getByTestId("snapshot-review-gates");
    expect(within(panel).getAllByRole("listitem")).toHaveLength(5);
    for (const gate of SNAPSHOT_REVIEW_REQUIRED_GATES) {
      expect(within(panel).getByText(gate)).toBeInTheDocument();
    }
    expect(panel).toHaveTextContent("NOT_VERIFIED");
    expect(panel).toHaveTextContent("WARNING");
    expect(panel).toHaveTextContent("Activation eligible: false");
    expect(panel).toHaveTextContent("완료 여부는 이 API로 판정할 수 없습니다");
    expect(within(panel).queryByRole("button")).not.toBeInTheDocument();
    expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
  });

  it("labels a superseded revision but never promotes it", () => {
    const old: SnapshotReviewPreview = {
      ...base, latest_revision_id: 12, is_latest: false, review_status: "SUPERSEDED",
    };
    expect(isSafeSnapshotReviewPreview(old)).toBe(true);
    render(<SnapshotReviewGates preview={old} />);
    expect(screen.getByTestId("snapshot-gate-revision")).toHaveTextContent("최신 #12로 대체됨");
    expect(screen.getByTestId("snapshot-review-gates")).toHaveTextContent("NOT_VERIFIED");
  });

  it("rejects missing, unknown, or duplicated required-gate payloads", () => {
    const samples = [
      [], ["MANUAL_CHANGE_REVIEW"],
      [...SNAPSHOT_REVIEW_REQUIRED_GATES.slice(0, 4), "UNKNOWN_GATE"],
      [...SNAPSHOT_REVIEW_REQUIRED_GATES.slice(0, 4), "MANUAL_CHANGE_REVIEW"],
      null, "MANUAL_CHANGE_REVIEW",
    ];
    for (const gates of samples) {
      const value = { ...base, required_gates: gates } as unknown as SnapshotReviewPreview;
      expect(isSafeSnapshotReviewPreview(value)).toBe(false);
    }
    const hostile = {
      ...base, required_gates: [...SNAPSHOT_REVIEW_REQUIRED_GATES.slice(0, 4), "secret://SENSITIVE"],
    } as SnapshotReviewPreview;
    render(<SnapshotReviewGates preview={hostile} />);
    const alert = screen.getByTestId("snapshot-gates-invalid");
    expect(alert).toHaveTextContent("확인할 수 없습니다");
    expect(screen.queryByText(/SENSITIVE/)).not.toBeInTheDocument();
    expect(screen.queryByTestId("snapshot-review-gates")).not.toBeInTheDocument();
  });

  it("rejects promoted readiness/activation and invalid internal verification flags", () => {
    const tampered: Partial<SnapshotReviewPreview>[] = [
      { activation_eligible: true as never },
      { preflight_status: "VERIFIED" as never },
      { candidate_package_readiness: "READY" as never },
      { snapshot_verified: false },
      { candidate_package_valid: false },
      { latest_revision_id: 10, is_latest: false },
      { latest_revision_id: 11, review_status: "REVIEW_REQUIRED" },
      { latest_revision_id: 9 },
    ];
    for (const fields of tampered) {
      expect(isSafeSnapshotReviewPreview({ ...base, ...fields })).toBe(false);
    }
  });
});
