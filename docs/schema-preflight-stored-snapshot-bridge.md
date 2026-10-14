# S-04-C-2B-2B — stored Snapshot to offline preflight contract bridge

**State: Draft implementation; not merged/deployed.**
Parent design PR #77 is still Draft and real military/DEMIS independent
preflight verification policy remains **unapproved and unavailable**.
Predecessor PR #78 (commit `1f30940`) only defined the offline comparison
contract and synthetic-only provider.

## Scope of this change

Add `app/services/schema_preflight_snapshot.py` with the internal,
non-HTTP function `check_stored_snapshot_preflight_contract`.

1. Call the existing S-04-C-2A `preview_snapshot_review` with exact
   source and revision. This verifies current immutable physical Snapshot,
   normalized fingerprint, counts, predecessor Diff and an offline v2
   `WARNING` candidate using the existing validator.
2. Refuse new assessment for superseded revisions; never call the provider
   for an already stale Snapshot.
3. Fetch the actual source-scoped row from DQA PostgreSQL and construct
   `SnapshotPreflightContext` server-side. Reject identity/fingerprint/
   capture-time inconsistencies. No client-supplied target, SQL, actor,
   privileges or `approved` flag is accepted by this service.
4. Invoke only the existing *offline* `check_preflight_evidence_contract`
   with an optional, explicitly injected provider. The default provider is
   `None` and yields `NO_TRUSTED_PROVIDER` without network or IO.
5. Re-read the latest revision and fingerprint *after* any injected
   provider evaluation. If capture or fingerprint changes during evaluation,
   discard the match and return `SUPERSEDED_SNAPSHOT`.
   This is a read-only best-effort race guard, **not** a durable approval
   lock or an authorization for a future positive verdict.
6. Unverifiable Snapshot raises the existing sanitized
   `SnapshotReviewError`; unexpected storage errors map to sanitized
   `SNAPSHOT_PREFLIGHT_CONTEXT_UNAVAILABLE`. Raw metadata, SQL,
   credentials and exceptions never enter the contract result.

All outputs remain strictly **non-authoritative**:
`preflight_status=NOT_VERIFIED`,
`independently_authenticated=false`,
`replay_protected=false`,
`revocation_checked=false`,
`catalog_ready=false`,
`activation_eligible=false`.
A synthetic match means only `STRUCTURAL_MATCH_ONLY`.

## No runtime surface change

- No API endpoint, scheduled job, background worker, CLI activation, or
  production evidence provider.
- No Alembic migration, model/policy/setting/permission changes.
- No Oracle or live DEMIS connection, patient rows or medical data.
- No human Review journal write, import, package READY upgrade,
  Query Template eligibility change or Catalog activation.
- No production issuer authentication, signature validation, revocation,
  durable nonce replay protection or DBA privileges attestation.
- The real DQA deployment stays on PR #76 Backend and Alembic
  `20261014_ss02`; PR #78/79 do not need Backend redeployment until
  an actually used runtime entrypoint is separately approved.

## Offline acceptance plan

`tests/test_schema_preflight_snapshot.py` covers default-unconfigured
provider, synthetic equal and different observations, latest/superseded
revisions, source isolation/missing revision, tampering of Snapshot/target/
diff/count/fingerprint, provider failure sanitization, newer capture or
fingerprint change during provider evaluation, no privileged actor/approval
claims and no Catalog / Snapshot mutation.

Run focused no-DB tests and existing contract, Snapshot preview/history,
Review-journal, and Catalog candidate validation suites in a detached
worktree. Do **not** run migrations or deploy. Real PostgreSQL, concurrency
proof and external issuer policy remain separate later gates.

**Next policy decision:** military/DEMIS DBA + security must choose a
trusted, independent source/issuer and complete metadata coverage,
authentication, signature/revocation, time, roles and replay constraints.
Only then design a positive `VERIFIED` path with a separate explicit
review/ready/import/activation gate and isolated persistence tests.
