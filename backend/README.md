# Backend

FastAPI application skeleton for DEMIS Query Assistant (DQA).

## Scope (PR 2)

Included:
- FastAPI app factory (`app.main:app`)
- Pydantic Settings (`app.core.config`)
- SQLAlchemy PostgreSQL session helpers (`app.adapters.db`)
- `/health` (liveness) and `/health/ready` (DQA DB readiness)
- pytest baseline
- development Dockerfile / Compose skeleton

Not included yet:
- Catalog Package import/validation
- Query Template registry
- LLM provider
- DEMIS read-only query execution

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

For trusted-LAN testing, set `DQA_LAN_BIND_IP` to this development PC's LAN IPv4
address. Keep `DQA_DB_BIND_IP=127.0.0.1`.

Example:

```text
DQA_LAN_BIND_IP=192.168.0.100
DQA_BACKEND_PORT=8000
DQA_DB_BIND_IP=127.0.0.1
```

Then the backend is reachable at `http://192.168.0.100:8000` from the trusted LAN,
subject to the host firewall. DNS and Traefik are not required.

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
