# Scripts

## Cloud Agent development environment

- `cloud-agent-install.sh`: idempotent install phase referenced by
  `.cursor/environment.json`. Provisions the toolchain for the planned stack
  (PostgreSQL, Python build tooling) and installs backend/frontend dependencies
  once their manifests exist. Also seeds a local `.env` from `.env.example`.
- `cloud-agent-start.sh`: per-boot start phase that brings up the local
  development PostgreSQL cluster and ensures the DQA application role/database
  exist. Safe to run repeatedly.

These scripts only prepare a local development database with a non-secret
development password; they never contain production credentials.

## On-prem / internal deployment

Operate on `docker-compose.onprem.yml` with a gitignored `.env.onprem`
(copied from `.env.onprem.example`):

| Script | Purpose |
|--------|---------|
| `dqa-migrate.sh` | start DB only, then `alembic upgrade head` (explicit; no backend) |
| `dqa-up.sh` | validate config, require Alembic at head, then build/up; no auto-migrate |
| `dqa-status.sh` | Compose ps + readiness checks |
| `dqa-logs.sh` | Compose logs (no secret echoing) |
| `dqa-down.sh` | stop services; preserves DB volume by default |
| `check-onprem-compose.sh` | static (+ optional Docker) auth/port/migration regression checks |

Shared helpers live in `dqa-common.sh` (including non-destructive migration head preflight).

Rules:
- no hard-coded server IP
- no secrets printed
- no auto-prune
- `down` does not delete volumes by default
- production Compose hardcodes fail-closed auth; `.env.onprem` cannot enable `dev_headers`
- unmigrated DB → `dqa-up.sh` fails before backend start

Optional development/LAN auth overlay:

```bash
docker compose -f docker-compose.onprem.yml -f docker-compose.onprem.dev.yml \
  --env-file .env.onprem up -d
```

Never enable `dev_headers` on a production host.

See `docs/runtime-and-deployment.md`.

Do not place credentials in scripts.
