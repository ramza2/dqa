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
| `dqa-backup.sh` | DQA PostgreSQL `pg_dump -Fc` + SHA-256 sidecar (DEMIS not included) |
| `dqa-backup-list.sh` | dry-run listing of local dump archives (never deletes) |
| `dqa-restore.sh` | fail-closed restore (`RESTORE` token + checksum + app stopped) |
| `dqa-audit-retention-status.sh` | aggregate audit window only (oldest/newest/count) |
| `check-onprem-compose.sh` | static (+ optional Docker) auth/port/migration/backup regression checks |

Shared helpers live in `dqa-common.sh` (including non-destructive migration head preflight).

Rules:
- no hard-coded server IP
- no secrets printed
- no auto-prune
- `down` does not delete volumes by default
- production Compose hardcodes fail-closed auth; `.env.onprem` cannot enable `dev_headers`
- unmigrated DB → `dqa-up.sh` fails before backend start
- backup/restore targets **DQA PostgreSQL only** (never DEMIS)
- restore does not auto-start application services
- no automatic backup deletion; no automatic audit purge

### Recommended backup sequence

```bash
./scripts/dqa-backup.sh
```

Output defaults to `<repo>/backups/dqa_<UTC>.dump` (+ `.sha256`). Override with
`DQA_BACKUP_DIR`. Relative paths resolve against the repository root
(`./backups` ⇒ `<repo>/backups`, not the shell CWD). Archives may contain
Catalog/template/audit operational metadata — store only in an approved
protected location. This foundation does not encrypt backups. Created
artifacts use restrictive modes (`0700` backup dir, `0600` dump/sidecar).

### Recommended restore sequence

```bash
./scripts/dqa-down.sh
./scripts/dqa-restore.sh /path/to/dqa_UTC.dump RESTORE
./scripts/dqa-up.sh
```

Restore refuses missing/mismatched checksums, non-`PGDMP`/invalid archives,
missing `RESTORE` token, and running backend/frontend. Validation happens
before DROP/CREATE. `pg_restore` uses `--single-transaction --exit-on-error`
so failures do not leave a partial schema. It does not run
`docker compose down -v` and does not auto-migrate after a failed/old restore.

Optional inspection:

```bash
./scripts/dqa-backup-list.sh
./scripts/dqa-audit-retention-status.sh
```

See `docs/runtime-and-deployment.md` and `docs/audit-retention-policy.md`.

Optional development/LAN auth overlay:

```bash
docker compose -f docker-compose.onprem.yml -f docker-compose.onprem.dev.yml \
  --env-file .env.onprem up -d
```

Never enable `dev_headers` on a production host.

Do not place credentials in scripts.

### Oracle mock E2E smoke test

Development/LAN Oracle mock integration only.

Run: `./scripts/dqa-oracle-mock-smoke.sh`

The smoke test verifies recommendation → parameter extraction → execution preview → read-only Oracle execution → audit lifecycle.

Default development fixture:
- source: `oracle_demis_mock`
- environment: `development`
- template: `demis.code-master.by-group`
- parameter: `cd_grp_id=DQA_TEST`
- expected rows: `3`

Values can be overridden with `DQA_SMOKE_*` environment variables.

The script uses the development `dev_headers` identity, does not print result rows or credentials, and must not be used against production or real clinical data.
