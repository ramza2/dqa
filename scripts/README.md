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

## Planned

- `deploy.sh`: Docker Compose + external Traefik deployment
- validation helpers where useful

Do not place credentials in scripts.
