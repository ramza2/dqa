# DQA Development Roadmap

The roadmap is intentionally split into small PRs.
Do not combine later phases simply to reduce PR count.

## Phase 0 - Bootstrap

### PR 1 - Project bootstrap
Scope:
- AGENTS.md
- Cursor Rules
- architecture/security/contract documents
- directory skeleton
- environment placeholder

No business feature implementation.

## Phase 1 - Catalog foundation

### PR 2 - Backend application skeleton
Scope:
- FastAPI application
- settings
- PostgreSQL connection
- health endpoint
- pytest baseline
- Docker development skeleton

### PR 3 - Catalog Package v2 validation
Scope:
- safe ZIP reader
- manifest parser
- version validation
- checksum validation
- required JSON validation
- tamper tests

No activation yet.

### PR 4 - Catalog import persistence
Scope:
- immutable package import revision
- normalized import metadata
- package validation status
- import history API

### PR 5 - Active Catalog management
Scope:
- activation rules
- READY/WARNING/BLOCKED policy
- active revision per source
- activation audit

## Phase 2 - Catalog exploration

### PR 6 - Catalog query APIs
Scope:
- tables
- columns
- relations
- indexes
- categories
- filters/search

### PR 7 - Catalog Explorer frontend
Scope:
- active package status
- table/column explorer
- relationship view
- package revision visibility

## Phase 3 - Query Template management

### PR 8 - Query Template registry
Scope:
- template + version model
- parameter schema
- draft CRUD
- Catalog compatibility metadata

### PR 9 - Approval workflow
Scope:
- IN_REVIEW / APPROVED / REJECTED
- enable/disable
- immutable approved version behavior
- approval audit

### PR 10 - SQL safety validator
Scope:
- single SELECT statement
- parser/tokenizer
- forbidden construct rejection
- declared parameter validation
- focused adversarial tests

No live DEMIS execution yet.

## Phase 4 - Recommendation

### PR 11 - LLM provider abstraction
Scope:
- OpenAI-compatible client interface
- structured response model
- timeout/error handling
- provider test doubles

### PR 12 - Template retrieval/recommendation
Scope:
- candidate retrieval
- LLM ranking
- confidence/clarification
- no execution

### PR 13 - Parameter extraction
Scope:
- structured extraction
- deterministic type/constraint validation
- clarification workflow

## Phase 5 - Read-only execution

### PR 14 - DEMIS read-only adapter
Scope:
- Oracle connection adapter
- read-only session
- timeout
- bound parameters
- row limit
- connection diagnostics

### PR 15 - Execution preview and execution service
Scope:
- executable eligibility checks
- preview
- approved execution
- normalized result
- failure categories

### PR 16 - Query Assistant frontend
Scope:
- natural-language request
- recommended template
- parameters
- execution preview
- explicit execution action
- result table

## Phase 6 - Audit and operations

### PR 17 - Audit log
Scope:
- request/execution audit
- catalog/template versions
- safe parameter logging policy
- audit search API/UI

### PR 18 - Deployment
Scope:
- Dockerfiles
- Compose
- external Traefik
- `.env.production`
- `scripts/deploy.sh`
- health/readiness checks

### PR 19 - Hardening
Scope:
- RBAC foundation
- rate/size limits
- operational error handling
- security regression suite
- backup/restore guidance

## Exit criteria before real DEMIS use

- Catalog Package import validated against real package
- approved template workflow operational
- unsafe SQL rejection demonstrated
- read-only DB privilege verified externally
- timeout/row cap verified
- audit enabled
- secrets not logged
- deployment health checks pass
