# Backend AGENTS.md

These rules apply to files under `backend/`.

## Stack

Target stack:
- Python 3.11+
- FastAPI
- SQLAlchemy
- Pydantic
- PostgreSQL for DQA application/catalog/template/audit state
- pytest

## Structure

Prefer:

```
backend/
  app/
    api/
    core/
    domain/
    models/
    schemas/
    services/
    repositories/
    mcp/              # MCP transport/registry/auth boundary (Phase 28+)
    adapters/
      catalog/
      connection_profile/
      db/
      demis/          # existing read-only DEMIS boundary
      llm/
    # Planned in later PRs (do not create prematurely):
    # schema_inspector/   metadata-only Oracle inspection boundary
    # controlled_write/   approved clinical Insert boundary
  tests/
```

Keep FastAPI route handlers thin.

Business rules belong in services/domain code.
Persistence belongs in repositories.
External systems belong in adapters.

MCP transport handlers must not access DEMIS or execute SQL. MCP tools call
application-service adapters only and reuse the same IdentityProvider / RBAC
fail-closed rules as Web APIs. Never trust caller-supplied `user_id` / `role` /
`permissions` as identity.

## Database access

**Existing DEMIS query execution stays read-only** through
`app/adapters/demis`. The current `OracleReadOnlyDemisAdapter`, read
Connection Profile/credentials, validator, preview, query/MCP execute endpoints
and tokens **must not** gain write capability.

A **future metadata-only Schema Inspector** may query approved Oracle
`ALL_*` catalog views only, using a separately constrained metadata
credential/profile and read-only sessions. It must not read patient rows,
perform DML/DDL, or infer capabilities beyond the active Catalog. Metadata
inspection is triggered explicitly by authorized admin action, not inline
with general query execution. Schema Snapshot → v2 Package validation →
immutable revision import → explicit READY activation is the reuse path.
No production inspection connection in this documentation-only PR.

A **future Controlled Write subsystem** is architecturally separate from both
the metadata inspector and read adapter. Only hospital/DEMIS-approved clinical
record Insert operations are in prospective scope. No generic SQL/CRUD and no
runtime write access until a separate reviewed implementation with institution
signoff, documented operation/field mapping, dedicated least-privilege
identity/secret, clinical approval-verification contract, complete testing
and default-disabled feature flag.

SNUH.AI/authorized clinical Workflow owns the **single clinician UI**, the
review/edit/approve-or-reject decision and the original approval audit.
DQA provides no duplicate clinician approval UI/HITL. A later write commit
must verify approval via an authenticated authoritative service lookup or
verifiable signed evidence for the *exact* document version/digest,
patient/Encounter, approver rights, operation and expiration/revocation.
Never accept caller-set `approved=true` or actor identity headers as proof.
DQA stores minimal write-execution audit/correlation IDs (not record bodies),
reuses neither read tokens nor read grants, and prevents duplicate inserts
through a durable idempotency/status/reconciliation design. Unknown commit
outcomes are reconciled, not blindly retried.

Never execute raw user-provided SQL.

Use bound parameters only.
Do not create SQL with user-value string concatenation.

All executable **read Query Templates** must pass the centralized SELECT-only
safety validator before reaching the read adapter. A future approved write
operation uses a separately defined typed operation registry and bound
parameters/official storage API, **never a Query Template exemption or
a bypass of the SELECT-only safety validator**.

Do not reuse the DQA PostgreSQL/`psycopg` stack as the DEMIS adapter.
Fake/test adapters are for tests only and must not be production-selectable.

Oracle (`dbms_type=oracle`) is the first production-selectable concrete adapter
(`OracleReadOnlyDemisAdapter`, python-oracledb thin mode only — no Instant Client).
Live mock/network/secret wiring remains an operator concern; this package does not
claim end-to-end DEMIS connectivity is validated in deployment.
Unsupported DBMS types remain fail-closed. Never resolve credentials before a
concrete adapter is selected.

Production credential resolution uses `EnvironmentCredentialResolver` (`env:` only)
gated by `DQA_DEMIS_CREDENTIAL_ENV_PREFIX`. Do not resolve credentials from
Connection Profile CRUD, diagnostics, or execution preview.

Query execution (`POST /api/v1/query-executions/execute`) re-runs eligibility,
writes durable audit on an independent DB session, and fail-closes when no
concrete DEMIS adapter exists. Never log/persist/LLM-egress result rows.

Form metadata (`GET /api/v1/query-executions/form`) is a QUERY_OPERATE projection
for parameter/environment UI without TEMPLATE_READ or profile-management grants.
It must not resolve credentials, connect to DEMIS, execute SQL, call LLM, or
write execution audit.

## Catalog authorization

Catalog APIs are permission-gated via `require_permission()`:

- `CATALOG_READ`: active Catalog pointers/metadata query, import history,
  activation history (granted to viewer/author/approver/query_operator/auditor)
- `CATALOG_MANAGE`: package validate / import / activate (administrator only)

`query_operator` must retain `CATALOG_READ` for Query Assistant source discovery.
Do not grant `CATALOG_MANAGE` to non-administrator roles.
Production still requires an approved IdentityProvider; Catalog RBAC only closes
authorization gaps under the existing provider abstraction.

Production FastAPI docs (`/docs`, `/redoc`, `/openapi.json`) are disabled when
`APP_ENV=production` (attack-surface reduction only; not an auth control).

## Catalog Package

Treat validated Catalog Package data and live DEMIS connectivity as separate
concerns. The **existing external package upload** and proposed internal
metadata-generated package share the same v2 manifest/checksum/schema
validation, import and activation lifecycle.

Package validation/import code must not require a live DEMIS DB connection.
The planned Inspector may connect only to retrieve metadata and produce a
candidate Snapshot/Package. Collection never auto-activates a revision or
makes unsafe data executable.

Imported package revisions must be immutable after successful import.
Only READY revisions may be activated through the existing authorized
activation path; preserve earlier active revision when collection/indexing
fails. Never copy the PoC Catalog DB/secret storage or v1 package writer
into DQA as an alternative source of truth.

## LLM

Use a provider interface.

The provider may return recommendations/parameter extraction, but execution eligibility must be decided by deterministic application code.

Never make LLM output the sole security control.

## Errors and logging

Return typed API errors.

Mask credentials, hosts, usernames, tokens, and connection strings where exposure is unnecessary.

Do not log result rows by default.

## Tests

Add focused pytest tests for each service boundary and security rule.
Use fixtures rather than production credentials.
