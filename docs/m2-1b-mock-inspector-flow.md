# M2-1B — Explicit selected Mock → Inspector metadata → Snapshot (2026-10-27)

## Contract

1. Choose a **registered** development-only Mock Connection Profile.
2. Explicit GET readiness (no Oracle connection or credential resolution).
   The server rejects inactive or non-pinned profiles, disabled Mock actions,
   missing Inspector configuration, target host/source/service/port mismatches,
   or the same read-query and metadata Inspector usernames.
3. Explicit POST inspection (empty body only) uses the *independent* server-side
   `DQA_SCHEMA_INSPECTOR_*` metadata account, Oracle `ALL_*` dictionary views
   and read-only transactions. Returns counts only, does not persist.
4. Explicit POST Snapshot capture (UUID + CAS predecessor only), re-checks all
   guards server-side and appends a revision through the existing history service.
   No Catalog import, READY, or activation.

## Credential boundary

- Query Profile: pinned `DEMIS_RO` and `env:DEMIS_SECRET_ORACLE_PASSWORD`.
- Metadata Inspector: **different Oracle username**, separately provisioned
  SELECT-only metadata privileges and an `env:DEMIS_INSPECT_SECRET_*` ref.
- Merely configuring a different username/ref **does not prove distinct
  Oracle grants or institutional approval**. A DBA must check actual grants.
- `DQA_SCHEMA_INSPECTOR_ENABLED=false` remains the default; Mock actions
  also require development/test + dev_headers + explicit opt-in.
- No new runtime secret or target endpoint is accepted from a client.
- The Mock's schema and database service must be configured server-side; never
  create/grant a user in actual DEMIS from this workflow.
- Prior S-05-C2 offline comparison is advisory, not execution authorization.
  This PR adds a **new, independent server-side execution guard**, not a
  persistent profile↔Inspector credential binding.

## Not included

Real DEMIS/replica authorization, DBA G0/G1 approval, Oracle privilege proof,
READY Package generation, Catalog activation, clinical SQL, FHIR/SNUH.AI,
automated Snapshot capture or scheduled background jobs.

## Acceptance

Isolated code/worktree tests first: backend
`test_m2_1b_mock_inspector_binding.py`, existing Inspector/Snapshot tests;
frontend `MockInspectorPanel.test.tsx`, existing ConnectionProfiles tests,
build and lint.

A live Oracle Mock end-to-end test additionally requires a **separately created
and approved synthetic metadata account with valid dictionary grants**,
independent credentials and settings supplied only inside the isolated
`dqa-m1-verify`-style stack. If absent, readiness must report blocked and no
live Inspector or Snapshot operation should be attempted.
