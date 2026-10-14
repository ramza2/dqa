# S-04-A Schema Snapshot Diff foundation

This is an **offline comparison foundation**, not a completed S-04
snapshot/review/activation workflow. No running DQA container is changed.

## Preconditions / scope

- Explicit **two** `SchemaSnapshot` DTOs from the same Oracle database/service
  and schema. Cross-target comparisons are rejected.
- The caller is responsible for the approved `source_name` association and
  the durable base/target revision identity; `SchemaSnapshot` contains only
  database/schema identifiers, **not** a Catalog source or immutable revision ID.
- No baseline -> **comparison unavailable**, not `identical=true`.
- No raw SQL/default expressions, PHI, credentials, query results or internal
  connection details. Only physical schema metadata.
- Reuses the exact canonical physical metadata payload and SHA-256 fingerprint
  from `schema_catalog_candidate.py`, including sorting nested FK/index
  column mappings by ordinal. Do **not** compare the SHA-256 to old Analyzer
  `schema_fingerprint`: its algorithm differs.
- Each change includes only object type, ADDED/REMOVED/CHANGED, tuple identity,
  and changed field **names**; never old/new values. Result is deterministic.
- Supports 6 types: TABLE, COLUMN, PRIMARY_KEY, UNIQUE_CONSTRAINT, FOREIGN_KEY,
  INDEX. PK and UNIQUE constraints are grouped by composite constraint
  identity, with ordered member columns. Diff includes table/column comments,
  types/nullable/precision and FK/index ordered mapping.
- SQL default values and index definitions are deliberately excluded, exactly
  like the v2 candidate fingerprint contract. Their changes are **not**
  detected here and must not be claimed as parity for those fields.
- Duplicate object identity, duplicate key ordinals or duplicate FK/index
  member ordinals fail closed instead of silently overwriting.

## API (Python, not HTTP)

```python
from app.services.schema_snapshot_diff import compare_schema_snapshots
result = compare_schema_snapshots(base_snapshot, target_snapshot)
assert result.total_changes == sum(count.total for count in result.counts.values())
```

`SnapshotDiff` includes database/schema identity, both DQA fingerprint
strings, `identical`, `total_changes`, counts by object type and ordered
immutable `SnapshotChange` entries. No writes or external requests.

## Boundary / next development PRs

1. **S-04-B**: explicit administrative capture, source-bound durable
   Snapshot/run revision repository. Reuse existing immutable Catalog Import
   Revision and active-pointer model rather than adding a competing Catalog
   activation mechanism. Include drift detection (CAS or equivalent),
   bounded retention, audit metadata and error recovery. All default-disabled
   until approved. Missing/corrupt prior baseline -> unavailable/blocked,
   never inferred as zero changes.
2. **S-04-C**: review/approval + independently verified preflight/readiness
   decision. Even a zero-diff result **cannot** upgrade a `WARNING` Package
   to `READY` by itself. A human must separately and explicitly activate
   an eligible imported Catalog revision; failed imports keep current active.
3. **S-05**: admin operational UI and status/diff history; S-06 parity,
   query/embedding rebuild acceptance and deployment cutover evaluation.

No patient rows, live DEMIS access, DEMIS Insert, runtime credentials,
new tables/migrations, REST endpoint, daemon or automatic activation in S-04-A.

## Mock evidence (completed before this PR)

- Oracle Mock baseline: TABLE 25, COLUMN 206, FOREIGN_KEY 40,
  INDEX 19, PK/UK constraints 31.
- DQA original Catalog READY Revision #1 physical mapping was compared
  to the Oracle Mock new candidate; initial 24 COLUMN `unique` differences
  corrected by PR #71, then COLUMN 206/206 identical.
- This is Oracle **Mock** parity, not military DEMIS authorisation or
  a completed live S-04 history/activation path.
