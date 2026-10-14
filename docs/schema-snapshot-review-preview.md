# S-04-C-2A — stored Snapshot review preview and offline candidate verification

**Status: Draft implementation, not merged or deployed.**
Predecessor S-04-C-1: PR #74 (`8fe486d`) merged, deployed to development DQA,
`20261014_ss01` remains current Alembic head.

## Goal and boundary

This PR provides a **read-only review preview** of a previously captured
immutable Schema Snapshot. It does **not** conduct an *independent* Oracle/DBA
metadata preflight, record a reviewer decision, promote the package to
`READY`, import a package, or activate the Catalog. Those are separate
approval-gated steps.

**API:**
`GET /api/v1/schema-inspector/snapshots/{revision_id}/review?source_name=...`

- Requires authenticated `CATALOG_READ`. Unknown / cross-source revision
  => 404. Malformed `source_name` => 422.
- Identifies `latest_revision_id`, `is_latest`, and
  `REVIEW_REQUIRED` vs `SUPERSEDED` (historical preview, not approval).
- Checks stored Snapshot v1 target identity, physical fingerprint, counts,
  key and FK/index ordered mappings, predecessor fingerprint and saved Diff
  integrity. Corrupt/unsupported/mismatched data fail closed with
  `409 SNAPSHOT_REVIEW_UNVERIFIABLE`; no raw values or error bodies.
- Reconstructs a temporary Catalog Package v2 from the stored (sanitized)
  Snapshot and calls the **existing validator**. This verifies structural
  compatibility only. Candidate ZIP bytes are neither returned nor persisted.
- Reports `candidate_package_valid=true`, `candidate_package_readiness=
  WARNING`, `preflight_status=NOT_VERIFIED`, and
  `activation_eligible=false` only after the checks succeed.
  The underlying offline candidate builder has always emitted `WARNING`.
- Reports existing persisted Diff classification (`NO_BASELINE` or
  `COMPARED`), `identical`, total changes, and reviewer pending requirements;
  use existing GET Snapshot detail to inspect changed object names/field names.
  No old/new field values, raw `snapshot_json`, SQL/default expressions,
  host/credentials, clinical rows or idempotency key in response.

### Required gates, still missing

1. `MANUAL_CHANGE_REVIEW`: authorized human reviews source, omissions,
   object changes and compatibility/impact. The API does not record approval.
2. `INDEPENDENT_PREFLIGHT`: independently collected metadata + DBA-approved
   scope/permissions and validation evidence with time, actor and target
   binding. Comparing a Snapshot to itself **does not satisfy this gate**.
3. `EXPLICIT_CATALOG_IMPORT`: validated immutable candidate import via
   existing Catalog import path only after policy is specified.
4. `READY_ELIGIBILITY_VERIFICATION`: independent verification of all
   requirements, not simply a matching fingerprint or zero changes. The
   existing candidate is `WARNING` and the current activation endpoint
   must continue rejecting it.
5. `MANUAL_ACTIVATION`: authenticated, authorized explicit action through
   the existing `READY+VALID` Catalog activation service. Never auto-switch.

The project still needs approved criteria for actual Oracle metadata preflight,
out-of-schema foreign keys, accepted omissions/exceptions, reviewer identity
and signoff, validity period and replay/staleness conditions. Do not invent
this policy or claim production military authorization.

## Tests and deployment limits

- New `backend/tests/test_schema_snapshot_review.py`: synthetic no-network
  verification, zero-diff remains WARNING, stale revision marker, corruption
  (payload/diff/count/target/version/previous), source isolation, authentication,
  CATALOG_READ authorization and sanitized 409.
- Regression with `tests/test_schema_snapshot_capture.py`,
  `tests/test_schema_snapshot_history.py`,
  `tests/test_schema_catalog_candidate.py`,
  `tests/test_schema_snapshot_diff.py`,
  `tests/test_schema_inspector_admin.py` and Catalog validator tests.
- No new Alembic migration, environment flag, scheduler, UI, Oracle connection,
  DEMIS patient query, Query Template change or Catalog pointer mutation.
- Test in a detached worktree. Real PostgreSQL tests only on an isolated
  disposable database (not `dqa-onprem`). Do not merge or deploy until
  separately reviewed and explicitly authorized.

## Next step (S-04-C-2B)

Define and implement **independent** preflight evidence and human approval
persistence, source/fingerprint/revision/CAS binding, expiration/recheck gates,
readiness policy + safe package promotion/import. Retain explicit activation
and previous Catalog revision on every failure. New write operations, if any,
require a separately reviewed Alembic migration and isolated PG tests.
