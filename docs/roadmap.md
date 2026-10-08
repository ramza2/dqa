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
Status: foundation contracts landed; Oracle thin-mode concrete adapter added
in a follow-up PR (`feat/oracle-readonly-adapter`).
Scope:
- DBMS-neutral adapter interface (`diagnostics`, `execute_readonly`)
- credential resolver protocol
- production `EnvironmentCredentialResolver` (`env:` + dedicated prefix boundary)
- Connection Profile snapshot eligibility (enabled + target metadata + credential ref)
- production factory fail-closed for unsupported DBMS; no DQA PG fallback
- test/fake adapter only (never production-selectable)
- read-only session/transaction / timeout / bound parameters / row limit contract
- sanitized connection diagnostics (`live_connection_tested=false` until probed)
- least-privilege assumptions documented

### PR 17c - Oracle read-only concrete adapter
Status: landed (`OracleReadOnlyDemisAdapter`, python-oracledb thin mode).
Scope:
- register `oracle` in the production concrete adapter factory
- bound SQL + parameters; `SET TRANSACTION READ ONLY` before SELECT
- call timeout; row_limit+1 truncation; rollback/close cleanup
- sanitized CONNECTION_FAILED / TIMEOUT / EXECUTION_FAILED mapping
- no Instant Client / thick mode; development-only Oracle mock network wiring is provided by `docker-compose.onprem.oracle-mock.yml`
- fake/test/mock/memory remain non-selectable

### PR 17b - Environment credential resolver
Status: landed on top of adapter foundation / preview.
Scope:
- `EnvironmentCredentialResolver` for `env:<NAME>` only
- `DQA_DEMIS_CREDENTIAL_ENV_PREFIX` allowlist boundary (default `DEMIS_SECRET_`)
- `create_credential_resolver(settings)` factory
- no DEMIS driver / connection / execute API
- Connection Profile and preview still store/check references only (no resolve)

### PR 18 - Execution preview and eligibility gate
Status: landed (`POST /api/v1/query-executions/preview`).
Scope:
- complete production execution eligibility gate (reusable service)
- executable eligibility checks (template/catalog/SQL/params/profile)
- preview API (`QUERY_OPERATE`); Oracle is production-selectable while unsupported DBMS/profile paths fail closed
- failure categories for preview/eligibility

### PR 18b - Query execution service + durable audit
Status: orchestration landed (`POST /api/v1/query-executions/execute`).
Scope:
- explicit user execution action (`QUERY_OPERATE`)
- re-run eligibility independently of preview
- durable audit writer (independent commit; fail closed on AUDIT_UNAVAILABLE)
- QUERY_REQUEST / QUERY_EXECUTION lifecycle (STARTED|SUCCEEDED|DENIED|FAILED)
- adapter factory + credential resolver wiring; normalized result response
- Oracle concrete adapter is selectable; unsupported DBMS, invalid profile, and unavailable credential paths remain fail closed
- fake adapter only via Python test DI (never HTTP/config/env selectable)
- result rows never persisted/logged/LLM-egressed

### PR 18c - Execution form metadata
Status: landed (`GET /api/v1/query-executions/form`).
Scope:
- QUERY_OPERATE-safe parameter + environment projection for Query Assistant
- no TEMPLATE_READ / CONNECTION_PROFILE_MANAGE grant
- no credentials / DEMIS / SQL execution / LLM / audit writes
- enabled environments only; incomplete → CONNECTION_PROFILE_INCOMPLETE;
  no concrete adapter → DEMIS_ADAPTER_UNAVAILABLE

### PR 19 - Query Assistant frontend
Status: landed (`feat/query-assistant-frontend`).
Scope:
- in-app Query Assistant / Catalog Explorer navigation (default: Assistant)
- natural-language recommendation → form metadata → optional AI extraction
- parameter confirmation, execution preview, explicit execute, result + audit_id
- Oracle mock development integration exercises preview/execute end to end
- production use remains blocked until production IdP and real DEMIS access/privilege validation are complete

## Phase 7 - Operations

### PR 20 - Internal/on-premise deployment
Status: foundation landed (`feat/onprem-deployment`).
Scope:
- frontend multi-stage production image (Node build → nginx SPA; `/api` proxy)
- production/on-prem Compose (`docker-compose.onprem.yml`)
- explicit LAN IP / frontend port binding; backend + DB not LAN-published
- internal-only DQA DB (no host ports; internal Compose network)
- production `APP_ENV=production` + `DQA_AUTH_PROVIDER=disabled` (fail closed)
- optional `docker-compose.onprem.dev.yml` for development/LAN `dev_headers` only
- `.env.onprem.example` + gitignored real `.env.onprem`; required DB password
- Alembic migrate workflow (`alembic upgrade head` via migrate profile/scripts)
- health/readiness (`/health`, `/health/ready`; frontend HTTP healthcheck)
- operational scripts: up / status / logs / down / migrate
- optional Traefik override only if an external-access requirement exists (not added)
- outstanding blockers documented: production IdP + real DEMIS endpoint/account/network/privilege validation

### PR 20b - Catalog RBAC hardening
Status: landed (`feat/catalog-rbac-hardening`).
Scope:
- `CATALOG_READ` / `CATALOG_MANAGE` permissions
- role mapping: read for viewer/author/approver/operator/auditor; manage admin-only
- protect active Catalog / query / import history / activation history reads
- protect package validate / import / activate management paths
- `query_operator` retains Catalog read for Query Assistant source discovery
- not part of this PR: production IdP, DEMIS adapter implementation, frontend redesign, or rate limiting

### PR 21 - Runtime security hardening (Phase 1)
Status: landed (`feat/runtime-security-hardening`).
Scope:
- nginx outer body-size limits (2m general; 55m Catalog validate/import)
- proxy/client timeout boundaries (backend query timeouts remain authoritative)
- CSP / Permissions-Policy / cache hygiene / `server_tokens off`
- production FastAPI `/docs` `/redoc` `/openapi.json` disabled
- error-sanitization regressions for representative secret markers
- request-field bound review for high-risk JSON endpoints
- on-prem checker no longer pip-installs dependencies
- rate limiting deferred pending traffic/concurrency requirements
- HSTS deferred to approved TLS termination
- not part of this PR: production IdP, DEMIS driver implementation, or frontend redesign

### PR 22 - DQA DB backup / restore + audit retention foundations
Status: landed (GitHub PR #28, `feat/db-backup-audit-retention`).
Scope:
- operator `dqa-backup.sh` (`pg_dump -Fc` via `dqa-db`, SHA-256 sidecar, `DQA_BACKUP_DIR`)
- fail-closed `dqa-restore.sh` (explicit `RESTORE` token, checksum, refuse while app up)
- dry-run `dqa-backup-list.sh` (no automatic backup deletion)
- audit retention policy document (append-only; duration not hardcoded; no auto purge)
- read-only `dqa-audit-retention-status.sh` (oldest/newest/count only)
- static regression checks for backup/restore safety boundaries
- no production IdP / real DEMIS connectivity / public audit DELETE API

### Oracle integration follow-ups
Status: landed (development/mock validation complete).

Landed follow-up work:
- GitHub PR #31: production-selectable `OracleReadOnlyDemisAdapter` using python-oracledb thin mode
- GitHub PR #32: local DEMIS Catalog Package ZIP excluded from Git
- GitHub PR #33: development-only Oracle mock Compose/network overlay with secret injection boundary
- GitHub PR #34: Oracle mock E2E smoke (`recommendation -> parameter extraction -> preview -> execute -> audit`)
- GitHub PR #35: security smoke for parameter validation, execution/audit RBAC, and `NAMES_ONLY` audit redaction
- GitHub PR #36: idempotent, fail-closed Oracle mock metadata bootstrap
- GitHub PR #37: isolated fresh-bootstrap contract test covering create -> review -> approve -> enable and repeat execution

Current boundary:
- Oracle mock integration is validated only for development/LAN testing
- no real DEMIS clinical data is used by these fixtures
- production remains fail closed until an approved IdP is configured
- real DEMIS endpoint, read-only account, network path, finalized Catalog Package, and database privilege validation remain external prerequisites

### PR 23 - Hardening (follow-up)
Status: repository-internal hardening complete; policy/site-dependent items deferred.

Implemented:
- operational error handling expansion
  - public DEMIS adapter errors use allowlisted codes + static sanitized messages
  - Recommendation/Parameter Extraction public errors use shared allowlisted
    contracts; unknown typed errors normalize to generic internal-error codes
  - Connection Profile, Catalog, Query Template, Audit, and execution typed
    errors use reviewed public contracts with fail-closed unknown-code handling
- security regression suite growth
  - recommendation LLM call-site egress denial regression
  - cross-cutting API role/permission matrix across representative protected routes
  - static route guard rejects direct typed-exception passthrough into public errors
- RBAC refinement across representative protected API surfaces
- data-egress policy enforcement
  - central fail-closed payload-class policy landed in GitHub PR #39
  - raw parameter-extraction request requires technical opt-in + explicit runtime approval assertion
  - query-result-row egress remains denied for all current LLM purposes
  - recommendation metadata egress is explicitly checked at the LLM call site
- public runtime/documentation state synchronized with the production-selectable
  Oracle read-only adapter and audited execution path

Deferred until policy/site inputs are confirmed:
- rate/size policy tuning based on internal concurrency / traffic requirements
- approved purge tooling after retention policy confirmation
- backup encryption after site key-management approval

### PR 24-A - Alembic historical schema adoption
Status: completed (merged via `hardening/alembic-historical-schema-adoption`).
Scope:
- Alembic revision `20261007_hist01` after `20260929_audit01`
- adopt create_all-era tables into Alembic ownership without data loss:
  `catalog_import_revisions`, `catalog_active_revisions`,
  `catalog_activation_events`, `query_templates`, `query_template_versions`,
  `query_template_review_events`
- fresh DB: `alembic upgrade head` creates full DQA schema
- legacy DB: existing tables are adopted only when schema-compatible
  (columns/PK/uniques/indexes/FKs); incompatible schemas fail closed
  (no stamp/ALTER/repair); compatible create_all rows preserved
- downgrade is non-destructive (revision pointer only)

### PR 24-B - Alembic-only schema lifecycle
Status: completed (merged via `hardening/alembic-only-schema-lifecycle`).
Scope:
- remove runtime `Base.metadata.create_all` / `init_db_schema` completely
- backend startup read-only Alembic head validation (fail closed; no schema mutation)
- shared checker: `app.adapters.db.migration_head` (+ CLI `alembic/check_at_head.py`)
- test DB fixtures bootstrap via `alembic upgrade head` only
- no new Alembic revision; head remains `20261007_hist01`
- authoritative workflow remains migrate then up (no auto-migrate)

### PR 25-A - Explicit Connection Profile live DEMIS probe
Status: completed (merged via `feat/live-demis-connection-probe`).
Scope:
- `POST /api/v1/connection-profiles/{profile_id}/test-connection` (administrator only)
- GET diagnostics remain configuration-only (no credential resolve / socket connect)
- production credential resolver + DEMIS adapter factory + Oracle `probe_readonly()`
- sanitized bounded failure categories; no probe result persistence
- no execution eligibility gate changes; no new Alembic revision

### PR 25-B - Production Readiness Report
Status: completed (merged via `feat/production-readiness-report`).
Scope:
- read-only operator preflight (`./scripts/dqa-readiness.sh --source-name ... --environment ...`)
- checks: migrations, auth provider, active Catalog, eligible Query Templates,
  Connection Profile, DEMIS adapter registration, live connectivity ACTION_REQUIRED,
  external read-only privilege ACTION_REQUIRED
- never resolves DEMIS credentials, never opens DEMIS sockets, never mutates schema/data
- distinct from `/health/ready` (DQA PostgreSQL reachability only)
- no HTTP readiness API in this PR; no new Alembic revision

### PR 26-A - Real DEMIS onboarding & acceptance runbook
Status: completed (merged via `docs/real-demis-onboarding-runbook`).
Scope:
- real DEMIS onboarding sequence
- automated vs external prerequisites
- explicit live probe interpretation
- DBA privilege verification checklist
- first controlled-query acceptance
- stop/rollback criteria
- acceptance record template
- no runtime behavior changes

### PR 26-B - Integrated DQA platform architecture rebaseline
Status: completed (merged via `docs/integrated-dqa-platform-architecture`).
Scope:
- redefine DQA as DEMIS Data Access & Query Platform
- SNUH.AI Agent Workflow → MCP → DQA → DEMIS target architecture
- integrate proven Schema Search PoC capabilities into DQA Data Discovery
- human Web Portal + MCP clients share one Safety/Execution/Audit Core
- define Approved Template path vs Structured Dynamic Query Plan path
- define Schema Analyzer / DQA bounded-context boundary
- define MCP tool surface at architecture level
- rebaseline subsequent implementation roadmap
- no runtime implementation in this PR

Authoritative target doc: `docs/integrated-platform-architecture.md`.

## Rebaselined implementation sequence (after 26-B)

Dependency order is fixed. Names may be refined; do not invert phases.

### Phase 27 - Data Discovery integration

- **PR 27-A — Data Discovery domain/contracts**
  Status: completed (merged via `feat/data-discovery-domain-contracts`).
  Catalog-derived search documents; source/revision scope; logical/physical
  identity; embedding model metadata; no UI; no search engine/API.
- **PR 27-B — Schema search engine integration**
  Status: completed (merged via `feat/data-discovery-search-engine`).
  Keyword / semantic / hybrid search; terminology + relation expansion;
  revision-scoped embedding lifecycle; no HTTP API / React UI yet.
- **PR 27-C — Data Discovery React Portal**
  Status: completed (merged via `feat/data-discovery-react-portal`).
  Schema Search, Schema Explorer, relation view, embedding/index status.

### Phase 28 - MCP integration

- **PR 28-A — MCP server foundation**
  Status: in progress (`feat/mcp-server-foundation`).
  Transport, tool registration, auth abstraction only; no new query semantics.
- **PR 28-B — Discovery MCP tools**
  `demis.search_schema`, `demis.describe_resource`.
- **PR 28-C — Template query MCP path**
  `demis.prepare_query`, `demis.execute_query` reusing Approved Template
  execution core (shared safety/audit; no parallel execute path).

### Phase 29 - Structured Dynamic Query

- **PR 29-A — Semantic Resource Model**
- **PR 29-B — Structured Query Plan contract + validation**
- **PR 29-C — Deterministic query compiler**
  No arbitrary SQL; parameterized SQL only; Catalog/allowlist driven.
- **PR 29-D — Dynamic Query execution integration**
  Shared eligibility/safety/audit core for MCP + Web.

### Phase 30 - Integrated acceptance / hardening

- Web/MCP equivalence tests
- Data Discovery regression vs former Schema Search PoC evidence
- security / adversarial tests
- Oracle mock E2E
- SNUH.AI integration acceptance (when interface exists)
- real DEMIS remains external acceptance
  ([real-demis-onboarding.md](real-demis-onboarding.md))

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
