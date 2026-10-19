import { describe, expect, it } from "vitest";
import { isSafeSnapshotReviewEvents } from "../utils/snapshotReviewJournal";
import type { SnapshotReviewEvent } from "../types/schemaSnapshot";

const sourceName = "synthetic_review_source";
const schemaFingerprint = "a".repeat(64);
const scope = { sourceName, revisionId: 7, schemaFingerprint };

const first: SnapshotReviewEvent = {
  id: 9, source_name: sourceName, snapshot_revision_id: 7,
  schema_fingerprint: schemaFingerprint, previous_review_event_id: null,
  decision: "ACKNOWLEDGED", reason_code: "REVIEWED_CHANGES",
  reviewed_by: "operator", reviewed_at: "2026-10-19T04:00:00Z",
};

describe("S-05-F read-only Snapshot review journal contract", () => {
  it("accepts empty and valid linked review history, without requiring optional false flags", () => {
    expect(isSafeSnapshotReviewEvents([], scope)).toBe(true);
    expect(isSafeSnapshotReviewEvents([first], scope)).toBe(true);
    const newest: SnapshotReviewEvent = {
      ...first, id: 14, previous_review_event_id: 9,
      decision: "CHANGES_REQUESTED", reason_code: "SCOPE_UNCLEAR",
    };
    expect(isSafeSnapshotReviewEvents([newest, first], scope)).toBe(true);
  });

  it("rejects malformed collections and foreign Source/Revision/Fingerprint", () => {
    for (const value of [
      null, {}, [null], "[]", [{ ...first, source_name: "other" }],
      [{ ...first, snapshot_revision_id: 77 }],
      [{ ...first, schema_fingerprint: "b".repeat(64) }],
    ]) {
      expect(isSafeSnapshotReviewEvents(value, scope)).toBe(false);
    }
  });

  it("rejects broken predecessor links, cycles, duplicated or out-of-order IDs", () => {
    const newer = { ...first, id: 12, previous_review_event_id: 9 };
    const bad = [
      [newer],
      [{ ...newer, previous_review_event_id: 8 }, first],
      [first, newer],
      [first, first],
      [{ ...newer, previous_review_event_id: 12 }, first],
      [{ ...first, previous_review_event_id: 10 }],
      [{ ...first, id: 0 }],
      [{ ...first, id: 1.5 }],
      [{ ...first, previous_review_event_id: -1 }],
    ];
    for (const row of bad) {
      expect(isSafeSnapshotReviewEvents(row, scope)).toBe(false);
    }
  });

  it("rejects invalid review decisions, reasons, actor or time", () => {
    for (const change of [
      { decision: "APPROVED" },
      { decision: "ACKNOWLEDGED", reason_code: "RECHECK_REQUIRED" },
      { decision: "CHANGES_REQUESTED", reason_code: "REVIEWED_CHANGES" },
      { reviewed_by: "" }, { reviewed_by: " padded " },
      { reviewed_at: "not-a-date" },
    ]) {
      expect(isSafeSnapshotReviewEvents([{ ...first, ...change }], scope)).toBe(false);
    }
  });

  it("never accepts a claim of completed Preflight, READY or activation in review metadata", () => {
    for (const flag of [
      "independent_preflight_verified", "catalog_ready", "catalog_activated",
    ] as const) {
      expect(isSafeSnapshotReviewEvents([{ ...first, [flag]: true }], scope)).toBe(false);
    }
    expect(isSafeSnapshotReviewEvents([{
      ...first, independent_preflight_verified: false,
      catalog_ready: false, catalog_activated: false,
    }], scope)).toBe(true);
  });

  it("accepts a 100-row truncated chain and rejects oversized results", () => {
    const rows = Array.from({ length: 100 }, (_, i) => ({
      ...first, id: 150 - i, previous_review_event_id: 149 - i,
    }));
    expect(isSafeSnapshotReviewEvents(rows, scope)).toBe(true);
    expect(isSafeSnapshotReviewEvents([...rows, first], scope)).toBe(false);
  });
});
