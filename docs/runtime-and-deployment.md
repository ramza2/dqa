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
| `APP_ENV` | **hardcoded** `production` in Compose (not overridable via `.env.onprem`) |
| `DQA_AUTH_PROVIDER` | **hardcoded** `disabled` in Compose (not overridable via `.env.onprem`) |
| LAN entry | frontend only |
| Backend / DB host ports | none |

Expected auth behavior:
- `/health` and `/health/ready` work
- protected APIs fail closed with `AUTH_PROVIDER_NOT_CONFIGURED` (503)
- this is an intentional blocker until an approved production IdentityProvider exists
- changing `.env.onprem` cannot enable development auth

Do not invent JWT/OIDC/SSO/reverse-proxy auth in this foundation.

### Mode B — development / LAN integration

Optional overlay: `docker-compose.onprem.dev.yml` (required for development auth)

| Setting | Value |
|---------|-------|
| `APP_ENV` | `development` (overlay override) |
| `DQA_AUTH_PROVIDER` | `dev_headers` (overlay override) |
| frontend image | Vite DEV (`frontend/Dockerfile.dev`), not production nginx |
| browser identity | `VITE_DQA_DEV_ACTOR` / `VITE_DQA_DEV_ROLES` (overlay only) |
| API proxy | `VITE_DEV_PROXY_TARGET=http://backend:8000` |
| LAN URL | unchanged: `${DQA_LAN_BIND_IP}:${DQA_FRONTEND_PORT}` → container `:80` |

Rules:
- production Compose hardcodes fail-closed auth; development auth requires the explicit overlay
- never enable `dev_headers` in production Compose
- never put actor/role values into production configuration
- production SPA builds never inject `VITE_DQA_DEV_*`
- Mode B is LAN development / integration testing only — never for production
- Mode B browser UI uses the overlay Vite DEV server so `X-DQA-Dev-*` headers are applied

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

Absence of a concrete DEMIS DBMS adapter for the selected profile is an
application capability state (`DEMIS_ADAPTER_UNAVAILABLE` /
`execution_available=false`). Oracle thin-mode adapter registration does not
by itself fail container liveness/readiness, and does not claim live DEMIS
connectivity has been operator-validated.

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

`APP_ENV` / `DQA_AUTH_PROVIDER` are not operator knobs in `.env.onprem` for Mode A.
Production Compose hardcodes them; the development overlay is the only supported auth override path.

Do not commit real DB passwords, API keys, LLM endpoints when sensitive, DEMIS passwords, or credential secret values.

## 6. Schema migrations

Production migration mechanism:

```bash
./scripts/dqa-migrate.sh
# equivalent: docker compose ... --profile migrate run --rm migrate
# runs: alembic upgrade head
```

`dqa-up.sh` does **not** auto-run migrations. It starts `dqa-db`, then runs a
non-destructive Alembic head check (`backend/alembic/check_at_head.py`). If the
database is not at every current Alembic head (including a fresh DB with no
`alembic_version`), it fails closed with:

```text
Database migration is required. Run ./scripts/dqa-migrate.sh first.
```

Recommended operational sequence:

```bash
./scripts/dqa-migrate.sh
./scripts/dqa-up.sh
```

Schema lifecycle is **Alembic-only** (Phase 24-B):
- Alembic head `20261007_hist01` owns the full DQA application schema
  (`connection_profiles`, `query_audit_events`, `catalog_import_revisions`,
  `catalog_active_revisions`, `catalog_activation_events`, `query_templates`,
  `query_template_versions`, `query_template_review_events`)
- runtime `Base.metadata.create_all` / `init_db_schema` are removed
- backend startup performs a read-only Alembic head check
  (`app.adapters.db.migration_head`, also used by `alembic/check_at_head.py`)
  and fails closed when the database is not at head — it never creates or
  alters tables
- authoritative order: **`./scripts/dqa-migrate.sh` then `./scripts/dqa-up.sh`**
- `20261007_hist01` adoption semantics (Phase 24-A): existing create_all-era
  tables are kept only when schema-compatible; incompatible legacy schemas
  fail closed without stamp/ALTER/repair
- downgrade of hist01 is intentionally non-destructive
- never run destructive downgrades automatically

## 7. Operational scripts

From repository root (requires Docker + `.env.onprem`):

```bash
./scripts/dqa-migrate.sh
./scripts/dqa-up.sh
./scripts/dqa-readiness.sh --source-name <source> --environment <env>
./scripts/dqa-status.sh
./scripts/dqa-logs.sh
./scripts/dqa-down.sh
./scripts/dqa-backup.sh
./scripts/dqa-backup-list.sh
./scripts/dqa-restore.sh /path/to/dqa_UTC.dump RESTORE
./scripts/dqa-audit-retention-status.sh
./scripts/check-onprem-compose.sh   # static (+ optional Docker) regression checks
```

Operator preflight sequence (Production Readiness Report is distinct from container health):

```bash
./scripts/dqa-migrate.sh
./scripts/dqa-up.sh
./scripts/dqa-readiness.sh --source-name oracle_demis_mock --environment development
# explicit live DEMIS probe remains a separate administrator action:
# POST /api/v1/connection-profiles/{profile_id}/test-connection
```

Behavior:
- `set -euo pipefail`
- secrets are not echoed
- no hard-coded server IP
- `down` does not delete the DB volume by default
- no auto-prune
- backup/restore never target DEMIS

### DQA database backup / restore

Scope: **DQA PostgreSQL only**. DEMIS source databases are outside this workflow.

Backup (`./scripts/dqa-backup.sh`):
- requires healthy `dqa-db` and Alembic at head
- runs `pg_dump --format=custom` inside the `dqa-db` container (no host client)
- writes `dqa_<UTC-timestamp>.dump` under `DQA_BACKUP_DIR` (default `<repo>/backups`)
- relative `DQA_BACKUP_DIR` values resolve against the repository root
  (`./backups` means `<repo>/backups`, not the operator CWD); absolute paths unchanged
- sets `umask 077`, backup directory mode `0700`, dump/sidecar mode `0600`
  (does not recursively chmod unrelated existing files)
- writes matching `.sha256` sidecar
- validates PostgreSQL custom-format magic (`PGDMP`) before treating the dump as good
- filenames never include passwords, hostnames, usernames, DEMIS identifiers,
  or patient/query data identifiers

Restore (`./scripts/dqa-restore.sh <dump> RESTORE`):
- deliberately destructive; requires explicit `RESTORE` confirmation token
- order: checksum → app stopped → DB healthy → copy → custom-format validation
  → DROP/CREATE → atomic `pg_restore` → Alembic head check
- verifies SHA-256 sidecar before touching data
- validates `PGDMP` magic plus `pg_restore --list` **before** DROP/CREATE
- restores with `--single-transaction --exit-on-error --no-owner --no-privileges`
  so a failed restore does not leave a partial application schema
- refuses while `backend` / `frontend` / `migrate` are running
- removes the container temp archive via `trap` on success and failure paths
- does **not** auto-start application services
- does **not** auto-run migrations after a failed/old restore
- does **not** run `docker compose down -v`

Recommended operator sequence:

```bash
./scripts/dqa-backup.sh
# ...
./scripts/dqa-down.sh
./scripts/dqa-restore.sh ./backups/dqa_UTC.dump RESTORE
./scripts/dqa-up.sh
```

Backup contents may include:
- Catalog revisions and activation history
- Query Templates / approvals
- Connection Profile non-secret metadata (`credential_secret_ref` string only)
- Query Audit Events
- Alembic version metadata

Backup contents must **not** include:
- DEMIS DB contents or query result sets
- DEMIS password values, LLM API keys, or env files

Backup files may contain sensitive operational metadata and audit records.
Store them only in an approved protected location. This foundation does **not**
encrypt backups and does **not** claim they are safe for external/untrusted
storage without an approved encryption policy.

Backup retention is site policy. `dqa-backup-list.sh` is a dry-run listing
helper only — it never deletes archives.

Audit retention duration remains an external governance decision. See
`docs/audit-retention-policy.md`. No automatic audit purge is implemented.

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
- `GET /health/ready` — readiness (DQA PostgreSQL reachable only)

Frontend healthcheck verifies the nginx HTTP serving endpoint.

`/health/ready` must not be confused with Production Readiness Report
(`./scripts/dqa-readiness.sh`). The report is an operator preflight over
migrations, auth, Catalog, templates, Connection Profile, and adapter
registration. It never claims container health and never opens DEMIS.

DEMIS adapter absence and LLM unavailability are capability/dependency diagnostics, not container health failures.

Connection Profile live connectivity is not probed at startup, via GET diagnostics,
or via the Production Readiness Report.
Administrators may run an explicit live probe with
`POST /api/v1/connection-profiles/{profile_id}/test-connection` after migrate/up.

## 10.1 Real DEMIS onboarding

For first-time real DEMIS linkage and controlled acceptance, follow the
authoritative runbook:

- [Real DEMIS Onboarding & Acceptance Runbook](real-demis-onboarding.md)

That document covers Catalog onboarding, Connection Profile registration,
explicit live probe interpretation, DBA privilege verification,
Production Readiness Report usage, first controlled query acceptance, and
stop/rollback criteria. It does not change runtime behavior.
Oracle mock E2E success is development evidence only and is not production
readiness.

## 11. Frontend nginx edge policy

The production frontend image uses nginx as the LAN entrypoint:

- general `/api/` body limit: `2m`
- Catalog package `validate` / `import`: `55m` (outer bound only; backend archive
  limit remains 50 MiB)
- explicit `proxy_send_timeout` / `proxy_read_timeout` / `client_*_timeout` /
  `send_timeout` (conservative; not unlimited)
- backend remains authoritative for SQL/query timeouts and Catalog archive limits
- CSP (`default-src 'self'`, no `unsafe-eval`, no CDN hosts) + Permissions-Policy
- `index.html` no-cache; hashed `/assets/` immutable long cache
- no `proxy_cache`
- `server_tokens off`
- no X-DQA-Dev-* identity header injection
- HSTS not enabled here — configure at the approved TLS termination point

Production backend also disables public OpenAPI docs (`/docs`, `/redoc`,
`/openapi.json`) when `APP_ENV=production`.

Rate limiting is deferred until hospital/internal concurrency expectations are
confirmed. Future limits should distinguish inexpensive reads, Catalog uploads,
LLM-backed endpoints, and query preview/execute.

Query execution limits are not configured by `QUERY_DEFAULT_*` / `QUERY_MAX_*`
environment variables (those knobs are unused and must not be advertised in
on-prem Compose / `.env.onprem.example`). Authoritative behavior:
- each approved Query Template defines `row_limit` and `timeout_seconds`
- hard maximums: timeout <= 300 seconds, row_limit <= 10_000
- execution eligibility validates limits server-side
- future site-wide tighter limits require an explicit policy feature

## 12. Persistence

DQA PostgreSQL stores:
- imported Catalog revisions
- activation state
- Query Templates and versions
- approvals
- execution/audit metadata
- connection profiles (non-secret)

Volume: Compose named volume `dqa_pgdata`.

## 13. Outstanding external blockers

This foundation does **not** make DQA ready for real DEMIS clinical use.

Still required externally:
1. Approved production authentication mechanism / IdentityProvider
2. Confirmed DEMIS DBMS and concrete read-only driver requirements
3. Approved TLS termination for real medical-data use
4. Approved audit/backup retention duration and storage/encryption policy

Live execution also still requires the full production execution gate in `docs/architecture.md`.
