import { describe, expect, it } from "vitest";
import { isSafeSnapshotHistoryList } from "../utils/snapshotHistoryList";
import type { SnapshotSummary } from "../types/schemaSnapshot";

const SOURCE = "synthetic_source";
const FP = "a".repeat(64);
const compared: SnapshotSummary = {
  id: 10, source_name: SOURCE, db_type: "oracle",
  database_name: "SYN_DB", schema_name: "SYN_OWNER",
  schema_fingerprint: FP, previous_revision_id: 9,
  captured_by: "operator", captured_at: "2026-10-19T00:00:00Z",
  counts: { tables: 2, columns: 10 },
  diff_status: "COMPARED", total_changes: 1,
};
const first: SnapshotSummary = {
  ...compared, id: 9, previous_revision_id: null,
  diff_status: "NO_BASELINE", total_changes: null,
};

describe("S-05-H Source-scoped Snapshot list runtime guard", () => {
  it("accepts an empty page and valid Snapshot-only rows", () => {
    expect(isSafeSnapshotHistoryList([], SOURCE)).toBe(true);
    expect(isSafeSnapshotHistoryList([compared], SOURCE)).toBe(true);
    expect(isSafeSnapshotHistoryList([first], SOURCE)).toBe(true);
  });

  it("accepts newest-first predecessor chains with gaps in globally allocated IDs", () => {
    expect(isSafeSnapshotHistoryList([compared, first], SOURCE)).toBe(true);
    const older = { ...first, id: 4 };
    const newer = { ...compared, previous_revision_id: 4 };
    expect(isSafeSnapshotHistoryList([newer, older], SOURCE)).toBe(true);
    // In a full page the last predecessor can point to the next page.
    const page = Array.from({ length: 50 }, (_, i) => ({
      ...compared, id: 100 - i, previous_revision_id: 99 - i,
    }));
    expect(isSafeSnapshotHistoryList(page, SOURCE)).toBe(true);
  });

  it("rejects null/non-array/malformed/oversized responses", () => {
    const cases: unknown[] = [
      null, {}, "not an array", [null], [undefined],
      { items: [compared] }, Array(51).fill(compared),
    ];
    for (const payload of cases) {
      expect(isSafeSnapshotHistoryList(payload, SOURCE)).toBe(false);
    }
    expect(isSafeSnapshotHistoryList([compared], SOURCE, 0)).toBe(false);
    expect(isSafeSnapshotHistoryList([compared], SOURCE, 51)).toBe(false);
  });

  it("rejects cross-Source revisions and unusable identity or dates", () => {
    const bad: unknown[] = [
      { source_name: "other" }, { id: 0 }, { id: 1.25 }, { id: "10" },
      { schema_fingerprint: "broken" }, { schema_fingerprint: "F".repeat(64) },
      { captured_at: "not-a-date" }, { database_name: null }, { schema_name: "" },
      { captured_by: "" }, { db_type: 55 },
    ];
    for (const patch of bad) {
      expect(isSafeSnapshotHistoryList([{ ...compared, ...patch }], SOURCE)).toBe(false);
    }
  });

  it("rejects incompatible baseline and diff status / total count combinations", () => {
    const bad: unknown[] = [
      { ...compared, previous_revision_id: null },
      { ...compared, previous_revision_id: 11 },
      { ...compared, total_changes: null },
      { ...compared, total_changes: -1 },
      { ...compared, total_changes: 1.5 },
      { ...compared, diff_status: "READY" },
      { ...first, total_changes: 0 },
      { ...first, previous_revision_id: 8 },
      { ...first, diff_status: "COMPARED" },
    ];
    for (const row of bad) expect(isSafeSnapshotHistoryList([row], SOURCE)).toBe(false);
  });

  it("rejects duplicate, out-of-order and broken predecessor links", () => {
    const invalid: unknown[] = [
      [compared, compared], [first, compared],
      [{ ...compared, previous_revision_id: 8 }, first],
      [compared, { ...first, id: 8 }],
      [compared, { ...first, source_name: "other" }],
    ];
    for (const payload of invalid) expect(isSafeSnapshotHistoryList(payload, SOURCE)).toBe(false);
  });

  it("rejects missing or invalid bounded metadata counts", () => {
    const cases: unknown[] = [
      null, [], "counts", { tables: -1 }, { tables: 1.5 },
      { tables: Number.MAX_SAFE_INTEGER + 1 }, { tables: "100" },
    ];
    for (const counts of cases) {
      expect(isSafeSnapshotHistoryList([{ ...compared, counts }], SOURCE)).toBe(false);
    }
  });
});
