import { describe, expect, it } from "vitest";
import { isSafeSnapshotDiffDetail, snapshotDiffCountRows } from "../utils/snapshotDiffOverview";
import type { SnapshotDetail } from "../types/schemaSnapshot";

const single: SnapshotDetail = {
  id: 10, source_name: "synthetic", db_type: "oracle",
  database_name: "MOCK_DB", schema_name: "MOCK_SCHEMA",
  schema_fingerprint: "a".repeat(64), previous_revision_id: 9,
  captured_by: "operator", captured_at: "2026-10-19T00:00:00Z",
  counts: { tables: 2, columns: 6 },
  diff_status: "COMPARED", total_changes: 1,
  diff_counts: { TABLE: { added: 0, removed: 0, changed: 1 } },
  changes: [{
    object_type: "TABLE", change_type: "CHANGED",
    object_key: ["MOCK_SCHEMA", "TB_SYN"], changed_fields: ["comment"],
  }],
};

describe("S-05-G metadata-only Snapshot Diff summary contract", () => {
  it("accepts a matching Changed count and emits deterministic object-type rows", () => {
    expect(isSafeSnapshotDiffDetail(single)).toBe(true);
    expect(snapshotDiffCountRows(single)).toEqual([
      { objectType: "TABLE", added: 0, removed: 0, changed: 1 },
    ]);
  });

  it("accepts valid added/removed/changed changes across object types", () => {
    const detail = {
      ...single, total_changes: 3,
      diff_counts: {
        TABLE: { added: 1, removed: 0, changed: 0 },
        COLUMN: { added: 0, removed: 1, changed: 1 },
      },
      changes: [
        { object_type: "TABLE", change_type: "ADDED", object_key: ["MOCK_SCHEMA", "TB_NEW"], changed_fields: [] },
        { object_type: "COLUMN", change_type: "REMOVED", object_key: ["MOCK_SCHEMA", "TB_OLD", "OLD_COL"], changed_fields: [] },
        { object_type: "COLUMN", change_type: "CHANGED", object_key: ["MOCK_SCHEMA", "TB_SYN", "VAL"], changed_fields: ["data_type"] },
      ],
    };
    expect(isSafeSnapshotDiffDetail(detail)).toBe(true);
    expect(snapshotDiffCountRows(detail)).toHaveLength(2);
  });

  it("distinguishes first Snapshot without baseline from a compared zero-change result", () => {
    const noBaseline = {
      ...single, previous_revision_id: null,
      diff_status: "NO_BASELINE", total_changes: null,
      diff_counts: {}, changes: [],
    };
    const noChanges = {
      ...single, total_changes: 0,
      diff_counts: { TABLE: { added: 0, removed: 0, changed: 0 } }, changes: [],
    };
    expect(isSafeSnapshotDiffDetail(noBaseline)).toBe(true);
    expect(isSafeSnapshotDiffDetail(noChanges)).toBe(true);
    expect(isSafeSnapshotDiffDetail({ ...noBaseline, total_changes: 0 })).toBe(false);
    expect(isSafeSnapshotDiffDetail({ ...noBaseline, diff_counts: noChanges.diff_counts })).toBe(false);
    expect(isSafeSnapshotDiffDetail({ ...single, previous_revision_id: null })).toBe(false);
  });

  it("rejects mismatching aggregate totals and incorrect per-object counts", () => {
    const invalid: unknown[] = [
      { ...single, total_changes: 2 },
      { ...single, diff_counts: { TABLE: { added: 0, removed: 1, changed: 0 } } },
      { ...single, changes: [] },
      { ...single, diff_counts: { TABLE: { added: 0, removed: 0, changed: -1 } } },
      { ...single, diff_counts: { TABLE: { added: 0, removed: 0, changed: 1.5 } } },
      { ...single, diff_counts: { TABLE: { added: 0, removed: 0, changed: Number.MAX_SAFE_INTEGER + 1 } } },
    ];
    for (const payload of invalid) expect(isSafeSnapshotDiffDetail(payload)).toBe(false);
  });

  it("rejects malformed, unknown and duplicated Diff changes", () => {
    const invalid: unknown[] = [
      null, [], {}, { ...single, diff_counts: null }, { ...single, changes: null },
      { ...single, diff_counts: { SQL: { added: 0, removed: 0, changed: 1 } } },
      { ...single, changes: [{ ...single.changes[0], object_type: "SQL" }] },
      { ...single, changes: [{ ...single.changes[0], change_type: "EXECUTE" }] },
      { ...single, changes: [{ ...single.changes[0], object_key: ["MOCK_SCHEMA"] }] },
      { ...single, changes: [{ ...single.changes[0], changed_fields: [] }] },
      { ...single, total_changes: 2, diff_counts: { TABLE: { added: 0, removed: 0, changed: 2 } },
        changes: [...single.changes, ...single.changes] },
    ];
    for (const payload of invalid) expect(isSafeSnapshotDiffDetail(payload)).toBe(false);
  });

  it("allows zero-count categories without pretending an unavailable baseline was compared", () => {
    const summary = {
      ...single, total_changes: 0,
      diff_counts: {
        TABLE: { added: 0, removed: 0, changed: 0 },
        FOREIGN_KEY: { added: 0, removed: 0, changed: 0 },
      },
      changes: [],
    };
    expect(isSafeSnapshotDiffDetail(summary)).toBe(true);
    expect(snapshotDiffCountRows(summary).map((r) => r.objectType)).toEqual(["TABLE", "FOREIGN_KEY"]);
  });
});
