export type QueryMeta = {
  revision_id: number;
  schema_fingerprint: string;
};

export function sameRevision(a: QueryMeta, b: QueryMeta): boolean {
  return (
    a.revision_id === b.revision_id && a.schema_fingerprint === b.schema_fingerprint
  );
}

/** Returns the shared snapshot meta, or null when responses disagree. */
export function assertSameSnapshot(metas: QueryMeta[]): QueryMeta | null {
  if (metas.length === 0) {
    return null;
  }
  const first = metas[0];
  for (let i = 1; i < metas.length; i += 1) {
    if (!sameRevision(first, metas[i])) {
      return null;
    }
  }
  return first;
}

export function matchesActive(
  meta: QueryMeta,
  active: { source_name: string; revision_id: number; schema_fingerprint: string },
  sourceName: string,
): boolean {
  return (
    active.source_name === sourceName &&
    sameRevision(meta, {
      revision_id: active.revision_id,
      schema_fingerprint: active.schema_fingerprint,
    })
  );
}
