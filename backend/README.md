# Backend

FastAPI backend for DEMIS Query Assistant (DQA).

## Current scope

Implemented:
- FastAPI app factory, settings, DQA PostgreSQL persistence, Alembic/runtime helpers
- Catalog Package validation/import/activation and Active Catalog query APIs
- Query Template registry, versioning, approval/enable workflow, and SQL safety validation
- OpenAI-compatible LLM provider abstraction for template recommendation and parameter extraction
- authentication/RBAC foundation with fail-closed production provider configuration
- Connection Profile management and environment-scoped credential reference boundary
- deterministic execution form/preview eligibility checks
- production-selectable Oracle thin-mode read-only DEMIS adapter
- audited read-only query execution with timeout/row-limit controls
- public error contracts and regression guards for exception-data leakage
- `/health` liveness and `/health/ready` DQA PostgreSQL readiness

## Layout

```text
backend/
├─ app/
│  ├─ api/routes/     # thin HTTP handlers
│  ├─ adapters/       # external systems (db / catalog / llm)
│  ├─ core/           # settings and shared config
│  ├─ domain/         # domain rules (later PRs)
│  ├─ models/         # SQLAlchemy models
│  ├─ repositories/   # persistence (later PRs)
│  ├─ schemas/        # API schemas
│  └─ services/       # application services (later PRs)
├─ tests/
├─ Dockerfile
├─ requirements.txt
└─ pyproject.toml
```

## Local development

```bash
# from repository root
python3 -m venv backend/.venv
source backend/.venv/bin/activate
cd backend && pip install -r requirements.txt

# requires local PostgreSQL matching .env (see scripts/cloud-agent-start.sh)
uvicorn app.main:app --reload --port 8000
```

Dependency pins live in `pyproject.toml`. `requirements.txt` is a thin
`-e .[dev]` entrypoint for local/Cloud Agent installs.

Or with Docker Compose (from repository root):

```bash
docker compose -f docker-compose.dev.yml up --build
```

By default the backend is exposed only on `127.0.0.1:8000` and PostgreSQL on
`127.0.0.1:5432`.

For GPU-server LAN testing, set `DQA_LAN_BIND_IP` to the GPU server's internal IPv4
address. Keep `DQA_DB_BIND_IP=127.0.0.1`.

Example:

```text
DQA_LAN_BIND_IP=192.168.0.100
DQA_BACKEND_PORT=8000
DQA_DB_BIND_IP=127.0.0.1
```

Then the backend is reachable at `http://192.168.0.100:8000` from the trusted LAN,
subject to the GPU server firewall. DNS and Traefik are not required.

Direct backend exposure is for development/integration testing only. The on-prem
production topology exposes the frontend as the LAN entrypoint and keeps the
backend and DQA PostgreSQL internal to Compose.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

## Health endpoints

- `GET /health` — process/API liveness
- `GET /health/ready` — DQA PostgreSQL connectivity

See also:
- `../AGENTS.md`
- `AGENTS.md`
- `../docs/architecture.md`
- `../docs/roadmap.md`

## Production boundary

Repository support for Oracle read-only execution does not by itself authorize or
prove real DEMIS clinical connectivity. Production use still requires an approved
IdentityProvider, operator-managed network/credential wiring, verified read-only
database privileges, approved TLS termination, and site retention/storage policy.
