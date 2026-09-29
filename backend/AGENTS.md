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
    adapters/
      catalog/
      connection_profile/
      db/
      demis/          # DBMS-neutral read-only DEMIS boundary (no concrete driver yet)
      llm/
  tests/
```

Keep FastAPI route handlers thin.

Business rules belong in services/domain code.
Persistence belongs in repositories.
External systems belong in adapters.

## Database access

Live DEMIS access must only occur through a dedicated read-only DB adapter
(`app/adapters/demis`).

Never execute raw user-provided SQL.

Use bound parameters only.
Do not create SQL with user-value string concatenation.

All executable Query Templates must pass a centralized safety validator before reaching the adapter.

Do not add a concrete DEMIS DBMS driver until requirements are confirmed.
Do not reuse the DQA PostgreSQL/`psycopg` stack as the DEMIS adapter.
Fake/test adapters are for tests only and must not be production-selectable.

Production credential resolution uses `EnvironmentCredentialResolver` (`env:` only)
gated by `DQA_DEMIS_CREDENTIAL_ENV_PREFIX`. Do not resolve credentials from
Connection Profile CRUD, diagnostics, or execution preview.

Query execution (`POST /api/v1/query-executions/execute`) re-runs eligibility,
writes durable audit on an independent DB session, and fail-closes when no
concrete DEMIS adapter exists. Never log/persist/LLM-egress result rows.

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
