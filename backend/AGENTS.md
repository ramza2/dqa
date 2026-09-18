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
      db/
      llm/
  tests/
```

Keep FastAPI route handlers thin.

Business rules belong in services/domain code.
Persistence belongs in repositories.
External systems belong in adapters.

## Database access

Live DEMIS access must only occur through a dedicated read-only DB adapter.

Never execute raw user-provided SQL.

Use bound parameters only.
Do not create SQL with user-value string concatenation.

All executable Query Templates must pass a centralized safety validator before reaching the adapter.

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
