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
Status: implemented (foundation)
Scope:
- source/environment -> live DEMIS target binding
- non-secret connection metadata
- secret-reference boundary
- enable/disable
- sanitized connection diagnostics
- no live query execution yet
- administrator-only `CONNECTION_PROFILE_MANAGE` API protection
- Alembic migration for `connection_profiles`

### PR 16 - Audit foundation
Status: implemented (foundation)
Scope:
- request/execution audit model
- active Catalog revision/fingerprint
- template/version
- actor
- sensitive parameter logging policy (`NAMES_ONLY`)
- no full result-set logging by default
- append-only `query_audit_events` + `AUDIT_READ` list/get API
- Alembic revision after `connection_profiles` (`20260929_cp01`)
- not yet wired into recommendation / extraction / execution paths

## Phase 6 - Read-only execution

### PR 17 - DEMIS read-only adapter
Status: foundation contracts landed (`app/adapters/demis`); concrete DBMS
adapter still blocked on confirmed DEMIS requirements.
Scope:
- DBMS-neutral adapter interface (`diagnostics`, `execute_readonly`)
- credential resolver protocol
- production `EnvironmentCredentialResolver` (`env:` + dedicated prefix boundary)
- Connection Profile snapshot eligibility (enabled + target metadata + credential ref)
- production factory fail-closed (`UNSUPPORTED_DBMS`); no DQA PG fallback
- test/fake adapter only (never production-selectable)
- first concrete DBMS implementation only after actual DEMIS requirements are confirmed
- read-only session/transaction (documented for future drivers)
- timeout / bound parameters / row limit request contract
- sanitized connection diagnostics (`live_connection_tested=false` until a driver exists)
- least-privilege assumptions documented
- no public execution API; not wired to recommendation / extraction / audit yet

### PR 17b - Environment credential resolver
Status: landed on top of adapter foundation / preview.
Scope:
- `EnvironmentCredentialResolver` for `env:<NAME>` only
- `DQA_DEMIS_CREDENTIAL_ENV_PREFIX` allowlist boundary (default `DEMIS_SECRET_`)
- `create_credential_resolver(settings)` factory
- no DEMIS driver / connection / execute API
- Connection Profile and preview still store/check references only (no resolve)

### PR 18 - Execution preview and execution service
Status: preview + eligibility gate landed (`POST /api/v1/query-executions/preview`);
actual execute endpoint / DEMIS call / audit wiring remain follow-up.
Scope:
- complete production execution eligibility gate (reusable service)
- executable eligibility checks (template/catalog/SQL/params/profile)
- preview API (`QUERY_OPERATE`); `execution_available=false` while no concrete DEMIS adapter
- explicit user execution action (not in this PR)
- approved read-only execution (not in this PR)
- normalized result (not in this PR)
- audit write (not in this PR)
- failure categories for preview/eligibility

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

### PR 20 - Internal/on-premise deployment
Scope:
- Dockerfiles
- Compose
- explicit LAN IP / port binding
- internal-only DQA DB exposure
- non-committed deployment environment
- deploy/status/logs/down workflow
- health/readiness checks
- optional Traefik override only if an external-access requirement exists

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
