# Frontend — Catalog Explorer

Operational Catalog Explorer for DEMIS Query Assistant (DQA).

This package is a **development UI** for browsing the currently active Catalog
revision. It is not a production deployment artifact yet.

## Stack

- React + TypeScript + Vite
- npm
- Vitest + React Testing Library

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

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `/api/v1` | API prefix used by the browser client |
| `VITE_DEV_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite dev-server proxy target for `/api` |

## Scripts

```bash
npm run dev
npm run lint
npm run test -- --run
npm run build
```

## Scope notes

Included:
- Active Catalog status (source / revision / readiness / fingerprint)
- Table search + detail
- Columns / relationships / indexes
- Categories read-only empty/list state

Not included in this PR:
- Catalog import / activation UI
- Query Template / SQL execution / LLM
- Authentication / RBAC
- Docker / Traefik deployment

## Relations note

Incoming relationships use `referenced_table_name` only (backend contract).
The UI additionally filters incoming rows by the selected table's `schema_name`.
