# Runtime and Deployment Plan

This is a design target, not yet an implemented deployment.

## Services

Expected production services:
- frontend
- backend
- dqa-db (PostgreSQL)

Live DEMIS DB remains external.

LLM endpoint remains external unless future requirements change.

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
