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
      demis/          # read-only DEMIS boundary (Oracle thin adapter + contracts)
      llm/
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

Live DEMIS access must only occur through a dedicated read-only DB adapter
(`app/adapters/demis`).

Never execute raw user-provided SQL.

Use bound parameters only.
Do not create SQL with user-value string concatenation.

All executable Query Templates must pass a centralized safety validator before reaching the adapter.

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

Treat imported Catalog Package data and live DEMIS connectivity as separate concerns.

Package validation/import code must not require a live DEMIS DB connection.

Imported package revisions must be immutable after successful import.

Activation should point to an imported revision rather than mutate it.

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
