# Runtime and Deployment Plan

This document defines the deployment direction for DQA.

## 1. Default deployment mode

DQA is initially operated as an internal/on-premise application.

Default access pattern:

```text
Trusted LAN client
    |
    | http://<DQA_LAN_IP>:<frontend/backend port>
    v
DQA containers
    |
    +--> DQA PostgreSQL (internal/loopback-only host exposure)
    |
    +--> operator-managed read-only DEMIS Connection Profile
```

Public DNS and Traefik are not required for this mode.

The current backend-only skeleton exposes the backend on the GPU server LAN for API testing. Once the frontend is implemented, prefer exposing only the frontend to the LAN and keeping the backend on the Compose network or server loopback.

## 2. Services

Expected services:
- frontend (later roadmap phase)
- backend
- dqa-db (PostgreSQL)

Live DEMIS DB remains external to the DQA stack and is reached through an operator-managed Connection Profile.

LLM endpoint remains external unless future requirements change.
Query result rows are not sent to the LLM by default.

## 3. Network exposure rules

Application services:
- current backend-only phase: backend may bind to the GPU server's explicitly configured LAN IPv4 for API testing
- after frontend implementation: prefer frontend as the LAN-facing service and keep backend internal/loopback
- use explicit host ports
- must not rely on wildcard public DNS

DQA PostgreSQL:
- stays on the Compose network for application access
- if a host port is needed for development tools, bind it to `127.0.0.1` by default
- must not be broadly exposed to the LAN or Internet

DEMIS database:
- is never published by DQA
- connectivity is defined by Connection Profile and site network policy

## 4. Environment files

Development:
- `.env` or local override, never committed
- LAN bind values may be provided through `.env`

On-premise/internal deployment:
- use a dedicated non-committed environment file when deployment automation is added

Template:
- `.env.example`

Current development bind variables:
- `DQA_LAN_BIND_IP`
- `DQA_BACKEND_PORT`
- `DQA_DB_BIND_IP`
- `DQA_DB_EXTERNAL_PORT`

## 5. Development Compose

Current backend skeleton:

```bash
docker compose -f docker-compose.dev.yml up --build
```

Default:
- backend -> `127.0.0.1:8000`
- PostgreSQL -> `127.0.0.1:5432`

For current integration testing, set `DQA_LAN_BIND_IP` to the existing GPU server's internal IPv4 address.

Example:

```text
DQA_LAN_BIND_IP=192.168.0.100
DQA_BACKEND_PORT=8000
DQA_DB_BIND_IP=127.0.0.1
```

Then another trusted LAN device may access:

```text
http://192.168.0.100:8000
```

subject to the host firewall.

## 6. Future deployment script target

The later deployment PR should provide commands equivalent to:

```text
deploy
status
logs
down
```

The internal deployment flow should:
1. validate environment
2. validate Docker/Compose availability
3. validate the selected LAN bind IP
4. validate Compose config
5. build images
6. deploy with remove-orphans
7. wait for backend/frontend health
8. print LAN access URLs and service status

Traefik checks must not be mandatory for internal/on-premise mode.

## 7. Optional external reverse proxy

If a future requirement explicitly needs external/public access, an additional Compose override may attach the application to an external Traefik network.

That optional mode may provide:
- Host-based routing
- TLS
- public DNS integration

It must remain separate from the default internal/on-premise Compose configuration.

## 8. Health model

Backend:
- liveness: process/API alive
- readiness: DQA PostgreSQL reachable and application initialized

DEMIS DB and LLM availability should normally be exposed as dependency diagnostics rather than make the application process itself unhealthy.

## 9. Persistence

DQA PostgreSQL stores:
- imported Catalog revisions
- activation state
- Query Templates and versions
- approvals
- execution/audit metadata

Imported raw package retention policy should be configurable.

## 10. Production query enablement

Deployment success alone does not enable live DEMIS querying.

Live execution requires the production execution gate defined in `docs/architecture.md`, including authentication/RBAC, an active READY Catalog revision, an enabled Connection Profile, approved Query Template, SQL/parameter validation, read-only DB privileges, limits, and audit persistence.
