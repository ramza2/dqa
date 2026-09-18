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
- zip-slip / duplicate-entry / zip-bomb defenses
- tamper tests

No activation yet.

### PR 4 - Catalog import persistence
Scope:
- immutable package import revision
- archive SHA-256 / manifest SHA-256
- normalized import metadata
- package validation status
- import history API

### PR 5 - Active Catalog management
Scope:
- READY-only activation policy
- WARNING/BLOCKED inspection behavior
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
- approval audit fields

### PR 10 - SQL safety validator
Scope:
- one statement
- SELECT / WITH ... SELECT allow rules
- reject FOR UPDATE / SELECT INTO
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
- no query-result data egress

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

## Phase 5 - Production execution prerequisites

### PR 14 - Authentication / RBAC foundation
Scope:
- authenticated actor abstraction
- roles/permissions foundation
- template author/approver/operator/auditor authorization points
- test/dev identity provider abstraction

### PR 15 - Connection Profile management
Scope:
- source/environment -> live DEMIS target binding
- non-secret connection metadata
- secret-reference boundary
- enable/disable
- sanitized connection diagnostics
- no live query execution yet

### PR 16 - Audit foundation
Scope:
- request/execution audit model
- active Catalog revision/fingerprint
- template/version
- actor
- sensitive parameter logging policy
- no full result-set logging by default

## Phase 6 - Read-only execution

### PR 17 - DEMIS read-only adapter
Scope:
- DBMS-neutral adapter interface
- first concrete DBMS implementation only after actual DEMIS requirements are confirmed
- read-only session/transaction
- timeout
- bound parameters
- row limit
- connection diagnostics
- least-privilege assumptions documented

### PR 18 - Execution preview and execution service
Scope:
- complete production execution gate
- executable eligibility checks
- preview
- explicit user execution action
- approved read-only execution
- normalized result
- audit write
- failure categories

### PR 19 - Query Assistant frontend
Scope:
- natural-language request
- recommended template
- parameters
- execution preview
- explicit execution action
- result table
- audit reference

## Phase 7 - Operations

### PR 20 - Production deployment
Scope:
- Dockerfiles
- Compose
- external Traefik
- `.env.production`
- `scripts/deploy.sh`
- health/readiness checks

### PR 21 - Hardening
Scope:
- rate/size limits
- operational error handling
- security regression suite
- backup/restore guidance
- audit retention
- RBAC refinement
- data-egress policy enforcement

## Exit criteria before real DEMIS use

- Catalog Package import validated against a real finalized package
- only READY Catalog revisions can be execution-active
- approved template workflow operational
- unsafe SQL rejection demonstrated
- authentication/RBAC enabled
- explicit Connection Profile bound to the active source/environment
- read-only DB privilege verified externally
- risky function/package EXECUTE privileges constrained
- timeout/row cap verified
- audit persistence enabled
- secrets not logged
- full result rows not sent to LLM by default
- deployment health checks pass
