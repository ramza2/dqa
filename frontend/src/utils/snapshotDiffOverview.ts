import type { SnapshotDetail } from "../types/schemaSnapshot";

/** Categories returned by the existing offline metadata-only Schema Diff. */
const OBJECT_TYPES = [
  "TABLE", "COLUMN", "PRIMARY_KEY", "UNIQUE_CONSTRAINT", "FOREIGN_KEY", "INDEX",
] as const;
type ObjectType = (typeof OBJECT_TYPES)[number];
type ChangeKind = "added" | "removed" | "changed";
type DiffCount = Record<ChangeKind, number>;

const KINDS = ["added", "removed", "changed"] as const;
const CHANGE_KIND: Record<string, ChangeKind> = {
  ADDED: "added", REMOVED: "removed", CHANGED: "changed",
};
const IDENTITIES: Record<ObjectType, number> = {
  TABLE: 2, COLUMN: 3, PRIMARY_KEY: 3, UNIQUE_CONSTRAINT: 3,
  FOREIGN_KEY: 3, INDEX: 3,
};

/**
 * Runtime-validate an independent GET /snapshots/{id} diff before rendering
 * it. The list, review preview, and event journal remain separate.
 */
export function isSafeSnapshotDiffDetail(value: unknown): value is SnapshotDetail {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const detail = value as Partial<SnapshotDetail>;
  if (
    (detail.diff_status !== "NO_BASELINE" && detail.diff_status !== "COMPARED")
    || !detail.diff_counts || typeof detail.diff_counts !== "object"
    || Array.isArray(detail.diff_counts) || !Array.isArray(detail.changes)
  ) return false;

  const rows = Object.entries(detail.diff_counts as Record<string, unknown>);
  if (rows.length > OBJECT_TYPES.length) return false;
  const counts = new Map<ObjectType, DiffCount>();
  let expectedTotal = 0;
  for (const [type, payload] of rows) {
    if (!OBJECT_TYPES.includes(type as ObjectType)
      || !payload || typeof payload !== "object" || Array.isArray(payload)) return false;
    const record = payload as Record<string, unknown>;
    const count = {} as DiffCount;
    for (const kind of KINDS) {
      const n = record[kind];
      if (typeof n !== "number" || !Number.isSafeInteger(n) || n < 0) return false;
      count[kind] = n;
      expectedTotal += n;
      if (!Number.isSafeInteger(expectedTotal)) return false;
    }
    counts.set(type as ObjectType, count);
  }

  if (detail.diff_status === "NO_BASELINE") {
    return detail.previous_revision_id === null
      && detail.total_changes === null
      && rows.length === 0
      && detail.changes.length === 0;
  }
  if (
    typeof detail.previous_revision_id !== "number"
    || !Number.isSafeInteger(detail.previous_revision_id)
    || detail.previous_revision_id <= 0
    || typeof detail.total_changes !== "number"
    || !Number.isSafeInteger(detail.total_changes)
    || detail.total_changes < 0
    || detail.total_changes !== expectedTotal
    || detail.changes.length !== expectedTotal
    || rows.length === 0
  ) return false;

  const observed = new Map<ObjectType, DiffCount>();
  for (const raw of detail.changes as unknown[]) {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return false;
    const change = raw as Record<string, unknown>;
    const type = change.object_type;
    const kind = change.change_type;
    if (typeof type !== "string" || !OBJECT_TYPES.includes(type as ObjectType)
      || typeof kind !== "string" || !(kind in CHANGE_KIND)
      || !Array.isArray(change.object_key)
      || change.object_key.length !== IDENTITIES[type as ObjectType]
      || !change.object_key.every((v: unknown) => typeof v === "string" && v.length > 0)
      || !Array.isArray(change.changed_fields)
      || !change.changed_fields.every((v: unknown) => typeof v === "string" && v.length > 0)
      || (kind === "CHANGED") !== (change.changed_fields.length > 0)
    ) return false;
    const itemType = type as ObjectType;
    const count = observed.get(itemType) ?? { added: 0, removed: 0, changed: 0 };
    count[CHANGE_KIND[kind]] += 1;
    observed.set(itemType, count);
  }
  for (const type of OBJECT_TYPES) {
    const expected = counts.get(type) ?? { added: 0, removed: 0, changed: 0 };
    const actual = observed.get(type) ?? { added: 0, removed: 0, changed: 0 };
    if (KINDS.some((kind) => expected[kind] !== actual[kind])) return false;
  }
  return true;
}

export function snapshotDiffCountRows(detail: SnapshotDetail): Array<{
  objectType: string; added: number; removed: number; changed: number;
}> {
  return OBJECT_TYPES.flatMap((objectType) => {
    const count = detail.diff_counts[objectType];
    return count ? [{
      objectType, added: count.added, removed: count.removed, changed: count.changed,
    }] : [];
  });
}
