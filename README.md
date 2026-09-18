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

## Initial stack

- Backend: FastAPI / Python 3.11+ / SQLAlchemy / Pydantic
- Frontend: React / TypeScript / Vite
- DQA DB: PostgreSQL
- LLM: OpenAI-compatible provider abstraction
- DEMIS connectivity: dedicated read-only DB adapter
- Deployment target: Docker Compose + external Traefik

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

Business code is intentionally not included in the bootstrap PR.

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
7. [Runtime and Deployment](docs/runtime-and-deployment.md)\n8. [Cursor Handoff Guide](docs/cursor-handoff.md)
9. [Bootstrap Design Review](docs/design-review.md)

## Development workflow

Feature work must use feature branches and pull requests.

Do not merge PRs automatically.
Merge only after tests/runtime validation and explicit approval.

The first implementation PR after bootstrap should be the backend application skeleton described in `docs/roadmap.md`.
