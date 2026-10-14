# S-04-C-1 — explicit administrator Snapshot capture API (Draft)

## Purpose and deployment state

This change integrates the S-01/S-02 Oracle **metadata-only** Schema Inspector
with S-04-B's append-only DQA `schema_snapshot_revisions` repository.

**Draft / not deployed.** S-04-B was deployed to the development DQA stack at
Alembic `20261014_ss01`; this change introduces **no new migration**.

The existing activated Catalog revision is authoritative; this capture does
not build, validate, import or activate a Catalog Package.

## API contract

`POST /api/v1/schema-inspector/snapshots/capture` requires
`CATALOG_MANAGE` (administrator) and body:

```json
{
  "capture_request_id": "3bccf311-2886-4f33-8cb6-26f6be5c3d61",
  "expected_previous_revision_id": null
}
```

- Supply a **new UUID** for a new capture. Retries of that same capture
  should reuse exactly the same UUID and expected predecessor. A consistent
  retry returns `created=false`, not another revision.
- `expected_previous_revision_id` is **required, even when null**.
  For the first capture, use `null`. For later captures, first query
  `GET /api/v1/schema-inspector/snapshots?source_name=...` and
  provide the newest recorded `id`. An intervening commit returns 409
  `STALE_SNAPSHOT_REVISION`; request-ID reuse with incompatible payload
  returns 409 `CAPTURE_REQUEST_REUSED`.
- No source, database, schema, host, credentials or SQL may be supplied.
  All Oracle target fields come from the **server operator's configured
  `DQA_SCHEMA_INSPECTOR_*` settings** and dedicated
  `DEMIS_INSPECT_SECRET_*` credential namespace.
- Authenticated user ID is captured as `captured_by`. Request ID is
  only an idempotency key, **not** identity/authentication evidence.
- Response gives revision id, fingerprint, counts, predecessor, diff status
  and total changes, `created`, `imported=false`,
  `activated=false`. No raw `snapshot_json`, connection host, SQL
  definitions, patient rows, credential, request UUID, or old/new column
  values are returned.
- Existing `GET /api/v1/schema-inspector/inspect` does not exist;
  **`POST /api/v1/schema-inspector/inspect` continues to return only
  counts and never persists.** Existing Snapshot history GETs remain
  separately gated by `CATALOG_READ` and source-scoped.

## Safety boundary

- The Inspector flag is **disabled by default**. Even if enabled,
  `APP_ENV=production` is explicitly blocked. Development/test
  administrator action is required; no scheduled/anonymous capture.
- The configured Oracle Inspector reads dictionary metadata only with
  the separate inspector account. It must not read clinical/business rows,
  change DEMIS, use query templates for unrestricted SQL, or send metadata
  to an LLM.
- Captured physical metadata and field-name-only diff are bound to an
  immutable DQA revision in a **committed** PostgreSQL transaction before
  the success response; errors roll back, map to reviewed public error
  codes and never return raw Oracle/PostgreSQL exceptions.
- Existing Catalog Import revisions and current active READY pointer
  remain unchanged. No package `READY` evaluation or activation is
  inferred from a zero-diff result. No new UI in this PR.

## Tests and next gates

1. Synthetic Pytest: `tests/test_schema_snapshot_capture.py`,
   `tests/test_schema_inspector_admin.py`,
   `tests/test_schema_snapshot_history.py`,
   `tests/test_schema_snapshot_diff.py`.
   Test administrator-only access, production/default-off policy,
   request field allowlist, UUID/CAS, sanitized output/error handling,
   no DB contact on disabled Inspector and previous multi-key FK/index
   Snapshot roundtrip.
2. Isolated **disposable PostgreSQL** acceptance: existing guarded
   `tests/test_schema_snapshot_history_pg.py`, now additionally
   exercises REST `POST capture` with a synthetic collector and verifies
   durable commit, retry, stale conflict, subsequent diff and GET history.
   Requires `DQA_PR73_ISOLATED_PG=1`, loopback host and
   `dqa_snapshot_pr73_*` database. Never run on DQA production/on-prem DB.
3. Optional Oracle Mock metadata-only E2E with approved development
   inspector secret; if attempted, use a separate disposable DQA DB and
   a controlled temporary container, not the active Catalog DB.
4. **Do not merge automatically**. Manual approval required. After merge,
   deployment still requires operator review; the current DQA on-prem
   development environment has the Inspector flag off by default.
5. S-04-C-2 separately defines review/preflight/readiness gates and
   offline v2 candidate promotion with explicit operator approval.
   S-05 separately provides admin capture and diff-history UI.

No real military DEMIS connection or clinical INSERT is authorized.
