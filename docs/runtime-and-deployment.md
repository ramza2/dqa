# Runtime and Deployment Plan

This is a design target, not yet an implemented deployment.

## Services

Expected production services:
- frontend
- backend
- dqa-db (PostgreSQL)

Live DEMIS DB remains external and is reached through an operator-managed Connection Profile.

LLM endpoint remains external unless future requirements change.
Query result rows are not sent to the LLM by default.

## Reverse proxy

Use the server's existing external Traefik network.

Production application containers should be attached to:
- internal application network as needed
- external Traefik network for routed services

Do not expose backend/frontend host ports unless required for controlled diagnostics.

## Environment files

Development:
- `.env` or local override, never committed

Production:
- `.env.production`, never committed

Template:
- `.env.example`

## Deployment script target

`scripts/deploy.sh` should eventually support:

```bash
./scripts/deploy.sh
./scripts/deploy.sh status
./scripts/deploy.sh logs
```

Deploy should:
1. validate environment
2. validate required Docker/Compose availability
3. verify Traefik external network
4. validate Compose config
5. build images
6. deploy with remove-orphans
7. wait for backend health
8. print service status

## Health model

Backend:
- liveness: process/API alive
- readiness: DQA PostgreSQL reachable and application initialized

DEMIS DB and LLM availability should normally be exposed as dependency diagnostics rather than make the application process itself unhealthy.

## Persistence

DQA PostgreSQL stores:
- imported Catalog revisions
- activation state
- Query Templates and versions
- approvals
- execution/audit metadata

Imported raw package retention policy should be configurable.


## Production query enablement

Deployment success alone does not enable live DEMIS querying.

Live execution requires the production execution gate defined in `docs/architecture.md`, including authentication/RBAC, an active READY Catalog revision, an enabled Connection Profile, approved Query Template, SQL/parameter validation, read-only DB privileges, limits, and audit persistence.
