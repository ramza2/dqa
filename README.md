# DEMIS Query Assistant (DQA)

DQA is the **target single deployable DEMIS Schema Intelligence, Data Access
and MCP Tool Platform**. The separate `demis-schema-search-poc` site remains a
development/parity reference during the approved migration and acceptance
process; it is **not** the final production dependency and must not be
decommissioned before G1/G5 cutover approval.

**Implemented code / development-verified (not real DEMIS approved):**
Catalog Package v2 import, immutable Catalog revision and explicit READY-only
activation; Data Discovery; approved read-only Query Template execution;
internal MCP Discovery/Template Query Tools; and a **default-disabled,
admin-gated metadata-only Oracle Schema Inspector**, append-only Snapshot
capture/history, diff/review and offline **WARNING-only** v2 candidate.
End-to-end site-approved Snapshot→READY→activation, clinical Insert and
production-exposed external MCP/FHIR/SNUH.AI integration are **not** complete.

**Target integrated architecture** (future work, not deployed):

```text
SNUH.AI clinician UI / Agent Workflow
  ↕ (approved clinical review/approval; AI task orchestration)
MedicalStandard FHIR Service ← PACS / other medical systems
  ↕ (FHIR data exchange; authorized MCP or internal REST)
DQA (single deployable platform)
  ├─ metadata-only Inspector [code; default-disabled, production gated]
  │    → Snapshot/review → WARNING candidate [code]
  │    → independent Preflight/READY → import/activate [future gated link]
  ├─ Catalog/Data Discovery / Query Template / MCP & REST
  ├─ approved read-only DEMIS Adapter            [implemented]
  └─ controlled clinical Insert Adapter           [planned; disabled]
       ↓
  DEMIS Oracle
```

SNUH.AI may call an approved DQA MCP boundary directly when negotiated, but
a request for FHIR-standardized data normally flows through the FHIR service.
DQA does **not** perform PACS integration or FHIR R4 conversion.
The **single clinician approval/rejection UI and clinical approval source of
truth** belong to SNUH.AI or a formally designated military approval system.
DQA would only validate trusted approval evidence and write execution status,
never prompt clinicians to re-approve within DQA.

Metadata collection does not itself authorize query execution: only an
explicitly activated, validated **READY** Catalog revision is authoritative.
Maintain the external Package Import path for offline/on-prem transfer.
Existing read execution and read credentials remain strictly SELECT-only.
Clinical Insert requires a new scoped, default-disabled write path plus
separate clinical, security and DEMIS site approval.

See [Integrated DQA Platform Architecture](docs/integrated-platform-architecture.md).

## Stack

- Backend: FastAPI / Python 3.11+ / SQLAlchemy / Pydantic
- Frontend: React / TypeScript / Vite
- DQA DB: PostgreSQL + pgvector
- LLM/Embedding: OpenAI-compatible provider abstraction / ModelOps Gateway configuration
- DEMIS connectivity: dedicated Oracle read-only DB adapter (implemented);
  Oracle metadata-only Inspector code (default-disabled / site approval pending);
  controlled write adapter not implemented
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
│  ├─ runtime-and-deployment.md
│  ├─ real-demis-onboarding.md
│  └─ integrated-platform-architecture.md
└─ scripts/
   └─ README.md
```

The current implementation includes Catalog management, approved Query Template
workflow, LLM-assisted recommendation/parameter extraction, deterministic
preview, audited read-only execution, Data Discovery (Schema Search / Schema
Explorer / Index Status), Query Assistant UI and internal Streamable HTTP MCP
Tools: `dqa.mcp_ready`, `demis.search_schema`, `demis.describe_resource`,
`demis.prepare_query`, `demis.execute_query`. The execution Tool requires
an explicit feature gate and production identity/ingress is **not** configured.
The Oracle metadata-only Inspector, Snapshot history/review and WARNING
candidate are implemented **as gated components**; site-approved inspector
activation, complete independent Preflight/READY integration, the business
Capability Registry, operational external MCP and clinical Insert tools
remain **planned or externally gated**.

## Key safety rule

The LLM may interpret intent, recommend an approved Query Template, and extract parameters.

It must not directly generate arbitrary SQL and execute it. The read
connection must never gain write rights.

**Current approved read path:**

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
2. [Architecture](docs/architecture.md) (current implementation)
3. [Integrated Platform Architecture](docs/integrated-platform-architecture.md) (target; approvals pending)
4. [Catalog Package Contract](docs/catalog-package-contract.md)
5. [Query Template Design](docs/query-template-design.md)
6. [Security](docs/security.md)
7. [Roadmap](docs/roadmap.md)
8. [Runtime and Deployment](docs/runtime-and-deployment.md)
9. [Real DEMIS Onboarding & Acceptance Runbook](docs/real-demis-onboarding.md)
10. [U-02 Development Verification & Cutover Handoff](docs/u02-integration-acceptance-handoff.md)
11. [U-02 External Decision / Approval Register](docs/u02-external-decision-register.md)
12. [Cursor Handoff Guide](docs/cursor-handoff.md)
13. [Bootstrap Design Review](docs/design-review.md)

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
policy decisions. **The real-DEMIS onboarding runbook certifies only the
current read path.** No real clinical Insert is permitted without a distinct
institutionally approved write runbook and acceptance.

Do not treat repository capability or Oracle mock E2E success as readiness for
real DEMIS clinical use. See
[Real DEMIS Onboarding & Acceptance Runbook](docs/real-demis-onboarding.md).

## Development workflow

Feature work must use feature branches and pull requests.

Do not merge PRs automatically.
Merge only after tests/runtime validation and explicit approval.

Use `docs/roadmap.md` for implemented history, current hardening status, and
policy/external prerequisites that remain outside repository-only changes.
