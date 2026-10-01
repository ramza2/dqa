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
- no Instant Client / thick mode; no live mock network wiring in-repo
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
- preview API (`QUERY_OPERATE`); `execution_available=false` while no concrete DEMIS adapter
- failure categories for preview/eligibility

### PR 18b - Query execution service + durable audit
Status: orchestration landed (`POST /api/v1/query-executions/execute`).
Scope:
- explicit user execution action (`QUERY_OPERATE`)
- re-run eligibility independently of preview
- durable audit writer (independent commit; fail closed on AUDIT_UNAVAILABLE)
- QUERY_REQUEST / QUERY_EXECUTION lifecycle (STARTED|SUCCEEDED|DENIED|FAILED)
- adapter factory + credential resolver wiring; normalized result response
- production still fail-closed (`DEMIS_ADAPTER_UNAVAILABLE`) until concrete DEMIS adapter
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
- live execute remains blocked until a concrete DEMIS adapter exists
  (`execution_available=false` / `DEMIS_ADAPTER_UNAVAILABLE`)

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
- outstanding blockers documented: production IdP + concrete DEMIS DBMS/driver

### PR 20b - Catalog RBAC hardening
Status: landed (`feat/catalog-rbac-hardening`).
Scope:
- `CATALOG_READ` / `CATALOG_MANAGE` permissions
- role mapping: read for viewer/author/approver/operator/auditor; manage admin-only
- protect active Catalog / query / import history / activation history reads
- protect package validate / import / activate management paths
- `query_operator` retains Catalog read for Query Assistant source discovery
- no production IdP / DEMIS adapter / frontend redesign / rate limiting

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
- no production IdP / DEMIS driver / frontend redesign

### PR 22 - DQA DB backup / restore + audit retention foundations
Status: Draft PR (`feat/db-backup-audit-retention`).
Scope:
- operator `dqa-backup.sh` (`pg_dump -Fc` via `dqa-db`, SHA-256 sidecar, `DQA_BACKUP_DIR`)
- fail-closed `dqa-restore.sh` (explicit `RESTORE` token, checksum, refuse while app up)
- dry-run `dqa-backup-list.sh` (no automatic backup deletion)
- audit retention policy document (append-only; duration not hardcoded; no auto purge)
- read-only `dqa-audit-retention-status.sh` (oldest/newest/count only)
- static regression checks for backup/restore safety boundaries
- no production IdP / DEMIS adapter / public audit DELETE API

### PR 23 - Hardening (follow-up)
Scope:
- rate/size policy tuning after concurrency requirements are confirmed
- operational error handling expansion
- security regression suite growth
- approved purge tooling after retention policy confirmation
- RBAC refinement (beyond Catalog)
- data-egress policy enforcement
- backup encryption after site key-management approval

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
