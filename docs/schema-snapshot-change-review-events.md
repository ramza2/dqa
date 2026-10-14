# S-04-C-2B-1 — append-only human change-review events (Draft)

**State: Not merged or deployed.** Requires an Alembic migration
`20261014_ss01 -> 20261014_ss02`; never run it on an existing DQA DB
without a backup, manual authorization and a separate rollback/recovery plan.
Current deployed development DQA is on `20261014_ss01`.

## Scope

This is a deliberately limited first part of S-04-C-2B. It records
**administrator acknowledgement or request for further changes** about
an immutable Schema Snapshot. It is not a DBA-signed **independent
preflight evidence verification**, does not approve Catalog READY,
does not generate a READY package, and cannot import, activate or modify
the authoritative active Catalog. It does not introduce any DEMIS DML.

- POST
  `/api/v1/schema-inspector/snapshots/{revision_id}/reviews?source_name=...`
  requires `CATALOG_MANAGE` and `DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED=true`
  in `APP_ENV=development/test`. All writes are disabled by default and
  remain disabled in `production` even if flag is set.
- GET the same path, `CATALOG_READ`, returns newest-first
  immutable events (bounded at 100). Wrong-source/missing revision => 404.
- Request:
  ```json
  {
    "review_request_id": "8e35b098-ec83-4a68-b260-6ca1be5a513b",
    "expected_schema_fingerprint": "<64 lowercase hexadecimal characters>",
    "expected_previous_review_event_id": null,
    "decision": "ACKNOWLEDGED",
    "reason_code": "REVIEWED_CHANGES"
  }
  ```
- Alternative decision `CHANGES_REQUESTED` requires `RECHECK_REQUIRED`
  or `SCOPE_UNCLEAR`. No client-supplied actor, permission, SQL, host,
  credentials, preflight result, READY status, or free-text evidence fields.
- The server derives `reviewed_by` from authenticated admin identity.
  `review_request_id` is idempotency only, not proof of authorization.
- Transactional same-source advisory lock shared with Snapshot Capture,
  latest-only snapshot revision guard and expected fingerprint.
  A separate expected_previous_review_event_id CAS prevents conflicting
  simultaneous human decisions. Identical request replay returns
  `created=false`; changed replay gives `REVIEW_REQUEST_REUSED`.
  After newer Snapshot capture a **new** old-revision review fails with 409;
  identical request replay remains safe.
- Before committing a new event, re-runs the read-only Snapshot
  integrity/candidate check from S-04-C-2A. Unverifiable Snapshot fails 409.
- Successful POST response is committed before returning and explicitly
  shows `independent_preflight_verified=false`,
  `catalog_ready=false`, `catalog_activated=false`.
  GET responses never include the idempotency UUID. No sensitive
  Oracle default SQL or patient records are stored in events.

## DB and safety

The `schema_snapshot_review_events` table stores minimal event metadata:
source + FK Snapshot revision + exact fingerprint, decision + reason code,
authenticated reviewer ID, previous event FK, request UUID and timestamp.
It has scoped uniqueness, bounded enums and source/revision index.
Migration is additive; downgrade refuses destructive deletion.

Do not confuse this *human acknowledgement* with independent preflight
attestation or final Catalog activation approval. The existing Catalog
READY-only activation rules remain unchanged. If the reviewer wishes to
overturn a prior acknowledgement, append a new `CHANGES_REQUESTED` event,
never edit/delete old events. A new Snapshot supersedes prior review scope.

## Acceptance

- Focused offline tests: `test_schema_snapshot_review_events.py` for
  disabled/production guards, HTTP RBAC, body allowlist, sanitized error
  codes and response indicators; plus existing S-04-C-1/2A regressions.
- Disposable isolated PostgreSQL acceptance after applying
  `20261014_ss02`: `test_schema_snapshot_history_pg.py`
  includes POST real commit, idempotent replay, same-UUID conflict, concurrent
  previous-event CAS, source isolation, review of stale Snapshot rejection,
  event history and active Catalog absence. Run only with the existing
  `DQA_PR73_ISOLATED_PG=1` guard and a loopback
  `dqa_snapshot_pr73_*` database. Never use live DQA PG.
- No new frontend and no real DEMIS or clinical data usage.

## Remaining S-04-C-2B gates (outside this PR)

1. Military/DEMIS DBA-approved independent inspection identity and scope,
   full metadata evidence format, independent origin verification, expected
   omissions/external FK policy, evidence age/expiration and revocation.
2. Independently verified preflight evidence linked to **exact Snapshot
   revision, fingerprint, source, target and review actor/time**, with
   anti-replay controls, independently authenticated verifier and audit.
3. Final human approval policy, separation of duties and a reversible
   authorization lifecycle; stale reviews/evidence must never be reusable.
4. Controlled READY candidate production using the *same existing* v2
   validator and explicit operator-driven Catalog import and READY-only
   manual activation. Abort and preserve current READY Catalog on any failure.
5. Operational IdP, trusted credential source and institution/DBA sign-off;
   development dev_headers/Oracle Mock are **not** production authorization.
