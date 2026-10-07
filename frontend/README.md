# Frontend — DQA operational UI

Operational UI for DEMIS Query Assistant (Catalog Explorer + Query Assistant).

## Stack

- React + TypeScript + Vite
- npm
- Vitest + React Testing Library
- Production image: multi-stage Node build → nginx (SPA + `/api` reverse proxy)

## Install

```bash
cd frontend
npm ci
```

## Development

Proxy API calls to a local backend (default `http://127.0.0.1:8000`):

```bash
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8000 npm run dev
```

GPU / on-prem runtime validation example (existing DQA backend on 8010):

```bash
VITE_DEV_PROXY_TARGET=http://127.0.0.1:8010 npm run dev -- --host 127.0.0.1
```

Optional local `dev_headers` identity (Vite DEV only; never production):

```bash
VITE_DQA_DEV_ACTOR=query-operator VITE_DQA_DEV_ROLES=query_operator npm run dev
```

Production builds strip `X-DQA-Dev-*` headers and must never inject
`VITE_DQA_DEV_ACTOR` / `VITE_DQA_DEV_ROLES`.

On-prem LAN integration (DEV overlay only — never production):

```bash
docker compose -f docker-compose.onprem.yml -f docker-compose.onprem.dev.yml \
  --env-file .env.onprem up -d --build
```

Uses `frontend/Dockerfile.dev` (Vite on `0.0.0.0:80`) while keeping the same
host publish `${DQA_LAN_BIND_IP}:${DQA_FRONTEND_PORT}:80`.

## Production Docker image

```bash
docker build -t dqa-frontend ./frontend
```

Runtime:
- serves the Vite SPA from nginx
- proxies `/api/` to the Compose `backend` service (same-origin; no external backend URL baked in)
- does not ship `node_modules` or the build toolchain

See repository `docker-compose.onprem.yml` and `docs/runtime-and-deployment.md`.

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `/api/v1` | API prefix used by the browser client |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite dev-server proxy target for `/api` |
| `VITE_DQA_DEV_ACTOR` | (unset) | DEV-only identity header value |
| `VITE_DQA_DEV_ROLES` | (unset) | DEV-only roles header value |

## Scripts

```bash
npm run dev
npm run lint
npm run test -- --run
npm run build
```

## Scope notes

Included:
- Query Assistant workflow (recommend → form → optional extract → preview → execute)
- Active Catalog Explorer (tables / columns / relations / indexes / categories)

Not included:
- Catalog import / activation UI
- Production IdentityProvider UI
- Real DEMIS clinical enablement. Oracle read-only adapter support exists, but
  production use still depends on approved IdentityProvider, operator
  network/credential wiring, read-only privilege validation, TLS termination,
  and site retention/storage policy.
