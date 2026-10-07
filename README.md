# DEMIS Query Assistant (DQA)

DEMIS Query Assistant is a separate consumer application for the Catalog Package produced by DEMIS Schema Analyzer.

The project goal is to provide safe catalog exploration and approved read-only query execution without allowing arbitrary LLM-generated SQL to execute directly.

## System boundary

```text
DEMIS Schema Analyzer
        |
        | Catalog Package v2
        v
DEMIS Query Assistant
        |
        | approved Query Template + bound parameters
        v
DEMIS DB (read-only)
```

DQA does not crawl or analyze DEMIS schema directly.
The imported and activated Catalog Package is the schema source of truth.

## Stack

- Backend: FastAPI / Python 3.11+ / SQLAlchemy / Pydantic
- Frontend: React / TypeScript / Vite
- DQA DB: PostgreSQL
- LLM: OpenAI-compatible provider abstraction
- DEMIS connectivity: dedicated read-only DB adapter
- Deployment target: Docker Compose internal/on-premise (LAN frontend; Traefik optional)

## Repository layout

```text
dqa/
├─ AGENTS.md
├─ .cursor/
│  └─ rules/
├─ .cursorignore
├─ .env.example
├─ backend/
│  ├─ AGENTS.md
│  └─ README.md
├─ frontend/
│  ├─ AGENTS.md
│  └─ README.md
├─ docs/
│  ├─ architecture.md
│  ├─ catalog-package-contract.md
│  ├─ query-template-design.md
│  ├─ security.md
│  ├─ roadmap.md
│  └─ runtime-and-deployment.md
└─ scripts/
   └─ README.md
```

The current implementation includes Catalog management, approved Query Template
workflow, LLM-assisted recommendation/parameter extraction, deterministic
preview, audited read-only execution, Catalog Explorer, and Query Assistant UI.

## Key safety rule

The LLM may interpret intent, recommend an approved Query Template, and extract parameters.

It must not directly generate arbitrary SQL and execute it.

Allowed path:

```text
Natural language
-> Catalog retrieval
-> APPROVED Query Template recommendation
-> parameter extraction
-> deterministic validation
-> execution preview
-> read-only execution
-> audit
```

## Documentation

Start here:

1. [AGENTS.md](AGENTS.md)
2. [Architecture](docs/architecture.md)
3. [Catalog Package Contract](docs/catalog-package-contract.md)
4. [Query Template Design](docs/query-template-design.md)
5. [Security](docs/security.md)
6. [Roadmap](docs/roadmap.md)
7. [Runtime and Deployment](docs/runtime-and-deployment.md)
8. [Cursor Handoff Guide](docs/cursor-handoff.md)
9. [Bootstrap Design Review](docs/design-review.md)

## On-prem deployment (foundation)

Production/on-prem Compose keeps the frontend as the LAN entrypoint and leaves
backend + DQA PostgreSQL internal. Production Compose **hardcodes**
`APP_ENV=production` and `DQA_AUTH_PROVIDER=disabled` (`.env.onprem` cannot
enable development auth). Development auth requires the explicit
`docker-compose.onprem.dev.yml` overlay.

```bash
cp .env.onprem.example .env.onprem   # set DQA_DB_PASSWORD and bind IP
./scripts/dqa-migrate.sh             # required before first up
./scripts/dqa-up.sh                  # refuses to start backend until Alembic is at head
./scripts/dqa-status.sh
```

See [Runtime and Deployment](docs/runtime-and-deployment.md) for Mode A/B,
migration caveats, and outstanding production prerequisites. Oracle thin-mode
read-only execution is implemented, but real DEMIS use still depends on an
approved production IdentityProvider, operator network/credential wiring,
read-only privilege validation, approved TLS termination, and retention/storage
policy decisions.

Do not treat repository capability as readiness for real DEMIS clinical use.

## Development workflow

Feature work must use feature branches and pull requests.

Do not merge PRs automatically.
Merge only after tests/runtime validation and explicit approval.

Use `docs/roadmap.md` for implemented history, current hardening status, and
policy/external prerequisites that remain outside repository-only changes.
