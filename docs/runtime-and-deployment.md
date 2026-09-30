# Runtime and Deployment Plan

This document defines the deployment direction for DQA.

## 1. Default deployment mode

DQA is initially operated as an internal/on-premise application.

Default access pattern:

```text
Trusted LAN client
    |
    | http://<DQA_LAN_BIND_IP>:<DQA_FRONTEND_PORT>
    v
frontend (nginx SPA + /api reverse proxy)
    |
    +-- Compose edge network --> backend (not LAN-published)
    |
    +-- Compose internal data network --> dqa-db (no host ports)
    |
    +--> operator-managed read-only DEMIS Connection Profile (external)
```

Public DNS and Traefik are not required for this mode.

## 2. Two operating modes

### Mode A — production / on-prem foundation

Compose: `docker-compose.onprem.yml`  
Env template: `.env.onprem.example` → gitignored `.env.onprem`

| Setting | Value |
|---------|-------|
| `APP_ENV` | `production` |
| `DQA_AUTH_PROVIDER` | `disabled` |
| LAN entry | frontend only |
| Backend / DB host ports | none |

Expected auth behavior:
- `/health` and `/health/ready` work
- protected APIs fail closed with `AUTH_PROVIDER_NOT_CONFIGURED` (503)
- this is an intentional blocker until an approved production IdentityProvider exists

Do not invent JWT/OIDC/SSO/reverse-proxy auth in this foundation.

### Mode B — development / LAN integration

Optional overlay: `docker-compose.onprem.dev.yml`

| Setting | Value |
|---------|-------|
| `APP_ENV` | `development` |
| `DQA_AUTH_PROVIDER` | `dev_headers` |

Rules:
- never enable `dev_headers` in production Compose
- never put actor/role values into production configuration
- production SPA builds never inject `VITE_DQA_DEV_*`
- Mode B API clients must supply `X-DQA-Dev-Actor` / `X-DQA-Dev-Roles`

Local Vite development against `docker-compose.dev.yml` remains supported separately.

## 3. Services

| Service | Role |
|---------|------|
| `frontend` | nginx static SPA; proxies `/api/` (and `/health`) to backend |
| `backend` | FastAPI; no `--reload`; readiness = DQA PostgreSQL reachable |
| `dqa-db` | DQA PostgreSQL; persistent named volume; Compose-internal only |
| `migrate` | one-shot profile (`--profile migrate`) running `alembic upgrade head` |

Live DEMIS DB remains external and is reached through an operator-managed Connection Profile.
LLM endpoint remains external unless future requirements change.
Query result rows are not sent to the LLM by default.

Absence of a concrete DEMIS DBMS adapter is an application capability state
(`DEMIS_ADAPTER_UNAVAILABLE` / `execution_available=false`). It must not fail
container liveness/readiness.

## 4. Network exposure rules

Production/on-prem Compose:
- frontend binds `${DQA_LAN_BIND_IP:-127.0.0.1}:${DQA_FRONTEND_PORT:-8080}`
- backend is not published to the host/LAN
- PostgreSQL has no host port publication
- do not expose `5432` or `8000` to `0.0.0.0`
- `data` network is `internal: true` (frontend cannot reach DB)

Development Compose (`docker-compose.dev.yml`):
- backend may bind to an explicit LAN IP for API testing
- PostgreSQL defaults to loopback host bind when a host port is needed

## 5. Environment files

| File | Purpose |
|------|---------|
| `.env.example` | local/dev placeholder |
| `.env.onprem.example` | on-prem placeholder (committed) |
| `.env` / `.env.onprem` | real values (gitignored) |

Production Compose requires an explicitly supplied `DQA_DB_PASSWORD` and fails if absent.
Do not default production DB passwords to `dqa` or `change-me`.

Do not commit real DB passwords, API keys, LLM endpoints when sensitive, DEMIS passwords, or credential secret values.

## 6. Schema migrations

Production migration mechanism:

```bash
./scripts/dqa-migrate.sh
# equivalent: docker compose ... --profile migrate run --rm migrate
# runs: alembic upgrade head
```

Do not rely on `create_all` as the documented production migration mechanism for new tables.

Historical caveat:
- Alembic currently owns `connection_profiles` and `query_audit_events`
- backend startup still runs `create_all` for older catalog/template tables until full migration ownership exists
- recommended fresh-DB order: **migrate first, then start backend**
- running `create_all` first, then Alembic, can fail when managed tables already exist
- never run destructive downgrades automatically

## 7. Operational scripts

From repository root (requires Docker + `.env.onprem`):

```bash
./scripts/dqa-migrate.sh
./scripts/dqa-up.sh
./scripts/dqa-status.sh
./scripts/dqa-logs.sh
./scripts/dqa-down.sh
```

Behavior:
- `set -euo pipefail`
- secrets are not echoed
- no hard-coded server IP
- `down` does not delete the DB volume by default
- no auto-prune

## 8. Development Compose

```bash
docker compose -f docker-compose.dev.yml up --build
```

Default:
- backend -> `127.0.0.1:8000`
- PostgreSQL -> `127.0.0.1:5432`

Run the Vite frontend separately for UI work:

```bash
cd frontend && npm run dev
```

## 9. Optional external reverse proxy

If a future requirement explicitly needs external/public access, an additional Compose override may attach the application to an external Traefik network.

That optional mode may provide Host-based routing, TLS, and public DNS integration.
It must remain separate from the default internal/on-premise Compose configuration.
No Traefik requirement has been confirmed for current on-prem use.

## 10. Health model

Backend:
- `GET /health` — liveness (process/API alive)
- `GET /health/ready` — readiness (DQA PostgreSQL reachable)

Frontend healthcheck verifies the nginx HTTP serving endpoint.

DEMIS adapter absence and LLM unavailability are capability/dependency diagnostics, not container health failures.

## 11. Persistence

DQA PostgreSQL stores:
- imported Catalog revisions
- activation state
- Query Templates and versions
- approvals
- execution/audit metadata
- connection profiles (non-secret)

Volume: Compose named volume `dqa_pgdata`.

## 12. Outstanding external blockers

This foundation does **not** make DQA ready for real DEMIS clinical use.

Still required externally:
1. Approved production authentication mechanism / IdentityProvider
2. Confirmed DEMIS DBMS and concrete read-only driver requirements

Live execution also still requires the full production execution gate in `docs/architecture.md`.
