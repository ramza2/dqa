# DQA Architecture

## 1. Goal

DEMIS Query Assistant (DQA) consumes a finalized Catalog Package from DEMIS Schema Analyzer and provides safe, auditable, read-only access through approved Query Templates.

DQA is not a schema crawler and is not a free-form Text-to-SQL execution engine.

## 2. System context

```text
DEMIS Schema Analyzer
        |
        | Catalog Package v2
        v
+------------------------------+
| DEMIS Query Assistant        |
|                              |
| Package Import / Validation  |
|        |                     |
|        v                     |
| Active Catalog Store         |
|   |              |           |
|   v              v           |
| Explorer    Template Registry|
|                  |           |
| User NL Request  |           |
|        |         |           |
|        v         |           |
| Intent / Retrieval           |
|        |                     |
|        v                     |
| Template Recommendation      |
|        |                     |
|        v                     |
| Parameter Extraction         |
|        |                     |
|        v                     |
| Deterministic Safety Gate    |
|        |                     |
|        v                     |
| Read-only DEMIS Adapter      |
|        |                     |
|        v                     |
| Results / Audit              |
+------------------------------+
             |
             v
        DEMIS DB
        read-only
```

## 3. Logical components

### 3.0 Authentication / RBAC

Foundation for protecting selected application endpoints:

```text
Request
  -> Identity Provider
  -> AuthenticatedActor
  -> Role / Permission resolver
  -> authorization dependency
  -> application service
```

Current provider:
- `DQA_AUTH_PROVIDER=disabled` (default): protected routes fail closed (503)
- `DQA_AUTH_PROVIDER=dev_headers`: development/test-only header assertion
  (`X-DQA-Dev-Actor`, `X-DQA-Dev-Roles`); rejected outside `development`/`test`

Routes authorize via permissions (`TEMPLATE_READ`, `TEMPLATE_AUTHOR`,
`TEMPLATE_APPROVE`, `QUERY_OPERATE`, `AUDIT_READ`, `CONNECTION_PROFILE_MANAGE`,
`CATALOG_READ`, `CATALOG_MANAGE`), not raw role strings.
`administrator` resolves to all declared permissions.

Role permission highlights:
- `CATALOG_READ`: active/imported Catalog metadata and activation history
  (granted to `viewer`, `template_author`, `template_approver`, `query_operator`,
  `auditor`; required so Query Assistant source discovery works for operators)
- `CATALOG_MANAGE`: package validate / import / activate (administrator only)

Authenticated `actor_id` is propagated into Query Template lifecycle metadata
(`created_by`, `approved_by`, review-event `actor`).

Catalog Package validate/import/activate and Catalog Explorer/query APIs are
permission-gated. Health endpoints remain unauthenticated.

Authentication is not execution permission. Query execution still requires
Connection Profile, SQL Safety, Active Catalog compatibility, read-only DEMIS
access, and audit.

Author vs approver permissions are separated; optional actor-level
separation-of-duty policy may be added later.

Production still requires an approved IdentityProvider; this Catalog RBAC
hardening only closes authorization gaps under the existing provider abstraction.

### 3.1 Package Import / Validation

Responsibilities:
- accept Catalog Package v2
- inspect ZIP root and manifest
- validate compatible package version
- verify all managed-file SHA-256 values
- parse core JSON files
- persist immutable import revision
- record validation result
- prevent activation of BLOCKED packages

It must not contact DEMIS DB.

### 3.2 Active Catalog Store

Stores imported package revisions and one active revision per configured source/environment.

Important properties:
- imported revision is immutable
- activation is explicit
- active revision records package version, source identity and schema fingerprint
- history is retained

Persistence split:
- `catalog_import_revisions`: immutable imported package rows
- `catalog_active_revisions`: current active pointer per `source_name` (unique)
- `catalog_activation_events`: append-only activation / revision-switch audit

Activation does not mutate import revision rows. Only READY + VALID revisions may be activated.

### 3.3 Connection Profile

A Connection Profile is separate from imported Catalog metadata.

Responsibilities:
- bind a logical Catalog source/environment to one live DEMIS target
- reference credentials through environment/secret management rather than Catalog data
- store non-secret compatibility metadata
- expose sanitized connection diagnostics
- support explicit enable/disable state

Implemented management API (`/api/v1/connection-profiles`):
- create / list / get / patch
- enable / disable (no delete; state is preserved)
- configuration-level sanitized diagnostics (`live_connection_tested=false`)
- unique `(source_name, environment)`
- `credential_secret_ref` stores a secret-store/env reference only
- password / token / full DSN values are never persisted or returned
- protected by `CONNECTION_PROFILE_MANAGE` (administrator only)

Activation of a Catalog revision does not automatically create or modify a live connection profile.
Live DEMIS connection tests and query execution are out of scope for this foundation.

Before execution, DQA must verify that:
- the selected Query Template is compatible with the active Catalog
- the connection profile is enabled
- the profile is bound to the intended source/environment
- the read-only connection test succeeds

### 3.4 Catalog Explorer / Search

Provides structured discovery of:
- tables
- columns
- comments
- PK/UK
- FK
- indexes
- categories
- ERD relationships

Search should initially be deterministic keyword/filter search.
Semantic retrieval may be added later if it provides clear value.

Query APIs read metadata from the **active** `CatalogImportRevision` JSONB
documents only (no live DEMIS crawling, no normalized catalog replica tables).
Responses include `source_name`, `revision_id`, and `schema_fingerprint` so
callers can tell which active revision was used.

### 3.5 Query Template Registry

Maintains versioned templates.

Execution eligibility:
- approval_status = APPROVED
- enabled = true
- compatible with active Catalog/source
- SQL passes deterministic safety validation

Templates must be versioned rather than overwritten in place after approval.

### 3.6 Intent / Recommendation

Flow:

```text
Raw NL request (local only)
  -> deterministic eligible-template retrieval
  -> metadata-derived safe intent terms
  -> eligible candidate metadata
  -> LLM ranking (advisory)
  -> deterministic validation
  -> recommendation / clarification
```

Candidate eligibility (before any LLM call) requires the current version to be:
- matching `source_name`
- `enabled=true`
- `approval_status=APPROVED`
- exact Active Catalog revision + fingerprint compatibility
- SQL Safety Validator PASS

Recommendation is **not** execution permission. Future execution still requires
RBAC, Connection Profile, read-only DEMIS access, audit, and runtime parameter
validation.

Privacy projection:
- raw `request_text` is never sent to the LLM
- only metadata-derived matched terms + candidate metadata egress
- SQL text, parameter values, and query result rows are never sent

LLM ranking output is untrusted: candidate IDs outside the deterministic set
fail closed. Low routing confidence (`RECOMMENDATION_MIN_CONFIDENCE`) or
`needs_clarification=true` returns clarification without a selected template.

Endpoint: `POST /api/v1/query-recommendations`

LLM access remains mediated by the provider abstraction:

```text
Application Service
       |
       v
LLMProvider interface
       |
       +--> OpenAICompatibleLLMProvider (httpx Chat Completions)
       |
       +--> test double (tests only)
```

Rules for this boundary:
- structured output is strict JSON parsed into a caller-supplied Pydantic model
- LLM output is untrusted input and never the sole security control
- no public arbitrary chat / Text-to-SQL endpoint
- provider does not generate or execute SQL
- query result rows are not sent to an LLM (no RESULT_SUMMARIZATION purpose)

LLM settings (`LLM_BASE_URL`, `LLM_MODEL`, optional `LLM_API_KEY`) are optional at
process start; completeness is validated only when `create_llm_provider` runs.

Some OpenAI-compatible/vLLM models (e.g. Qwen3) may need an explicit
chat-template thinking control for clean structured JSON. Optional
`LLM_ENABLE_THINKING` is included in the wire payload only when set; the default
is to send no extension. The provider never strips `<think>` tags or repairs
model output.

Known limitation: initial retrieval is privacy-first lexical matching over
template metadata. Synonyms / paraphrases / morphology outside metadata may
yield no-match clarification. Embeddings and raw-NL egress are out of scope.
Recommendation LLM payloads use a conservative character budget
(`MAX_PROMPT_USER_JSON_CHARS`); this is a projection cap, not a tokenizer
guarantee. Oversize prompts fail closed instead of being sent.


### 3.7 Parameter Extraction / Validation

Flow after a selected Query Template version:

```text
Recommendation
  -> selected template_id + version_id
  -> eligibility recheck (APPROVED + enabled + current version
     + Active Catalog compatibility + SQL Safety PASS)
  -> raw-request egress policy gate
  -> structured parameter extraction (LLM, advisory)
  -> deterministic parameter validation
  -> resolved parameters / clarification
  -> [future execution gate]
```

Endpoint: `POST /api/v1/query-parameters/extract`

Rules:
- Parameter Extraction is **not** execution permission
- `version_id` must equal the template's current version (stale recommendations fail)
- executable SQL is never generated, modified, or run in this step
- SQL text is never sent to the LLM
- no DEMIS DB access and no extraction-result persistence
- LLM may propose values only for declared parameter names
- undeclared parameter names from the LLM fail closed
- final validity is decided by deterministic validation, not the model

Deterministic validator (`services/parameter_validation.py`) checks:
- required / optional / default application
- types: string, integer, decimal, boolean, date, datetime, enum,
  string_list, integer_list
- pattern, min/max, allowed_values, min_items/max_items
- unresolved names and constraint failures become clarification
  (`needs_clarification=true`, HTTP 200), not system errors

Raw natural-language request text may reach the LLM only when
`LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST=true`. Default is `false`
(403 when parameters exist). Templates with an empty parameter schema skip
the LLM and succeed without enabling egress.

Extraction prompt payloads use a conservative character budget
(`MAX_EXTRACTION_PROMPT_USER_JSON_CHARS`); this is not a tokenizer
guarantee. Oversize prompts fail closed without calling the provider.
Parameter schemas are not dropped to shrink the prompt.

Parameters are bound variables for future execution, never
string-concatenated into SQL.

### 3.8 SQL Safety Gate

Central deterministic component.

Minimum checks:
- single statement (no empty/leading/repeated terminators; ≤1 trailing `;`)
- SELECT-only
- no DML/DDL/TCL/DCL
- no procedural block
- no unapproved template
- row/timeout limits
- parameters match declared definitions

`require_sql_safe()` enforces fail-closed (raises on unsafe). Inspection APIs
may call `validate_sql_safety()` and still return `safe=false` without raising.

The safety gate runs even for approved templates.

### 3.9 Read-only DEMIS Adapter

Adapter package: `app/adapters/demis` (DBMS-neutral contracts plus the
production-selectable Oracle thin-mode implementation).

The adapter interface is DBMS-neutral.
**Oracle (`dbms_type=oracle`) is registered as a concrete production adapter**
using python-oracledb thin mode (`OracleReadOnlyDemisAdapter`). Other DBMS types
remain fail-closed. Do not reuse DQA PostgreSQL/`psycopg` as the DEMIS adapter.
This registration does **not** claim live DEMIS/mock network connectivity has
been validated in an operator environment.

Implemented:
- `ReadOnlyDemisAdapter` protocol: `diagnostics(...)`, `execute_readonly(...)`
- request DTO: approved SQL text + bound parameter map + `timeout_seconds` + `row_limit`
- result DTO: `columns`, `rows`, `row_count`, `truncated`, `elapsed_ms`
- sanitized diagnostics DTO (no host/port/user/DSN/credential ref)
- `CredentialResolver` protocol (`credential_secret_ref` → opaque runtime material)
- production `EnvironmentCredentialResolver` for explicit `env:<NAME>` refs only,
  gated by `DQA_DEMIS_CREDENTIAL_ENV_PREFIX` (default `DEMIS_SECRET_`)
- `create_credential_resolver(settings)` factory for the production resolver boundary
- production factory `create_readonly_demis_adapter(...)` consuming an enabled
  Connection Profile snapshot + credential resolver (fail-closed for unsupported DBMS)
- Oracle thin-mode concrete adapter (bound parameters, `SET TRANSACTION READ ONLY`,
  call timeout, row_limit+1 truncation, sanitized errors; no Instant Client)
- test-only fake adapter / fake resolver (never selectable via production factory)

Credentials are never resolved during Connection Profile CRUD/diagnostics or
execution preview. Resolver invocation remains behind concrete adapter selection;
unsupported DBMS still returns `UNSUPPORTED_DBMS` without reading environment secrets.

Adapter responsibilities:
- connection lifecycle
- read-only session/transaction where supported
- bound parameter execution only (no value interpolation into SQL)
- statement timeout
- result row cap
- one execution request per call (no multi-statement bypass)
- normalized result metadata
- sanitized errors / bounded failure categories
- least-privilege DEMIS account remains mandatory outside the adapter

The adapter must not:
- generate or modify SQL
- accept natural-language input
- own Query Template approval
- call LLM
- write audit events
- log, persist, or put result rows into exceptions
- fall back silently to DQA PostgreSQL

Factory behavior for unsupported DBMS: validate profile eligibility (enabled,
target metadata, credential ref *presence*), reject forbidden fake/test kinds,
then raise `UNSUPPORTED_DBMS` **before** calling `CredentialResolver.resolve`.
Credentials are resolved only after a concrete adapter (currently Oracle) is
selected.

No query generation occurs here.

### 3.9.1 Execution preview / eligibility gate

`POST /api/v1/query-executions/preview` (requires `QUERY_OPERATE`) runs the
deterministic production eligibility gate without contacting DEMIS.

Reusable service: `evaluate_execution_eligibility(...)` (shared by preview and
execute). It re-checks template existence/source, current version,
APPROVED+enabled, Active Catalog revision/fingerprint match, SQL Safety PASS,
parameter schema + undeclared-key rejection + deterministic validation, and an
enabled Connection Profile with complete non-secret adapter metadata.

Preview may succeed while live execution remains blocked for unsupported DBMS:
- `execution_available=false`
- `execution_blockers` may include `DEMIS_ADAPTER_UNAVAILABLE`
  when no concrete adapter is registered for the profile `dbms_type`
  (Oracle is registered; other DBMS types remain unavailable)

Preview does **not** resolve credentials, instantiate a live adapter, execute
SQL, call LLM, return SQL/host/user/DSN, or write audit events.
`row_limit` / `timeout_seconds` come only from the approved template version.
Application hard maximums are currently `timeout_seconds <= 300` and
`row_limit <= 10_000` (`MAX_TIMEOUT_SECONDS` / `MAX_ROW_LIMIT` in
`app.adapters.demis.types`); eligibility validates these server-side.
Unused `QUERY_DEFAULT_*` / `QUERY_MAX_*` environment variables are not
supported runtime knobs.
Responses that include resolved parameter values use `Cache-Control: no-store, private`.

### 3.9.1b Execution form metadata

`GET /api/v1/query-executions/form` (requires `QUERY_OPERATE`) returns a narrow
execution-oriented projection for Query Assistant after template recommendation:
approved template identity, safe parameter definitions (including schema
`default` / `sensitive`, never runtime values), and enabled environments with
`execution_available` / sanitized blockers.

Query Assistant may obtain this metadata through `QUERY_OPERATE` without
`TEMPLATE_READ` or `CONNECTION_PROFILE_MANAGE`.

Eligibility (no parameter values required): template exists / source match /
current version / enabled + APPROVED / Active Catalog revision+fingerprint /
SQL Safety PASS / `sql_text` within `MAX_SQL_TEXT_LENGTH` / parameter schema
parses.

Environment discovery loads Connection Profiles internally by `source_name`:
- disabled profiles are omitted
- enabled incomplete profiles are returned with
  `execution_available=false` and `CONNECTION_PROFILE_INCOMPLETE`
- complete profiles without a concrete DEMIS adapter use
  `DEMIS_ADAPTER_UNAVAILABLE`

Never returns SQL, host/port/dbms/username/database, credential refs, profile
ids, approval notes, or author metadata. Does not resolve credentials, create
adapters, execute SQL, call LLM, or write audit. Headers:
`Cache-Control: no-store, private` and `Pragma: no-cache`.

### 3.9.2 Query execution orchestration

`POST /api/v1/query-executions/execute` (requires `QUERY_OPERATE`) is the
explicit user execution action. It always re-runs
`evaluate_execution_eligibility()` and never trusts a prior preview response.

Orchestration (`execute_query`):
1. generate `audit_id`; durable-append `QUERY_REQUEST` / `STARTED`
2. re-evaluate eligibility; on failure durable-append `DENIED` (no DEMIS access)
3. if `execution_available=false`, durable-append `DENIED` with
   `DEMIS_ADAPTER_UNAVAILABLE` and fail closed (no credential resolution)
4. on eligibility success, durable-append `QUERY_REQUEST` / `SUCCEEDED`
5. durable-append `QUERY_EXECUTION` / `STARTED` (if this fails, no credentials)
6. build `ConnectionProfileSnapshot` server-side; create credential resolver +
   read-only adapter via production factories (factory failures append
   `QUERY_EXECUTION` / `FAILED`)
7. build `ReadonlyQueryRequest` only from approved `version.sql_text`,
   resolved parameters, and approved timeout/row_limit (unexpected contract
   validation failures append `FAILED` with sanitized `EXECUTION_FAILED`)
8. call `adapter.execute_readonly()` exactly once; success → durable-append
   `SUCCEEDED` (elapsed/row_count/truncated + names only); adapter/runtime
   failure → durable-append `FAILED` with sanitized `failure_category`

Eligibility also rejects approved `sql_text` longer than the adapter
`MAX_SQL_TEXT_LENGTH` contract (`TEMPLATE_NOT_ELIGIBLE`) before any
credential/adapter access, without echoing SQL.

Caller-controlled request fields match preview (`source_name`, `environment`,
`template_id`, `version_id`, `parameters`). Caller-supplied SQL, catalog
revision/fingerprint, connection profile id, row_limit, timeout, actor/audit
metadata, and credentials are rejected.

Response includes `audit_id`, catalog/template/version/profile ids, columns,
rows, row_count, truncated, elapsed_ms. It never returns SQL, host/port,
username, database/service name, credential ref/value, DSN, or raw driver
errors. Headers: `Cache-Control: no-store, private` and `Pragma: no-cache`.

**Oracle is production-selectable** via the registered thin-mode adapter when
the Connection Profile `dbms_type` is `oracle` and credentials resolve. Live
connectivity still depends on operator network/secret wiring and is not claimed
validated by this repository change alone. Unsupported DBMS types fail closed
after eligibility (`DEMIS_ADAPTER_UNAVAILABLE`) before credential resolution.
Fake/test adapters remain injectable only at the Python test boundary.

Result privacy: rows may contain medical/sensitive data; they are never logged,
never persisted, never placed in exceptions, never sent to an LLM, and
summarization is not added.

### 3.10 Result Handling

Return:
- columns
- rows up to allowed limit
- truncation indicator
- elapsed time
- template/version
- active Catalog fingerprint
- audit reference

Query result rows are not sent to an LLM by default.
Optional result summarization may be added only after an explicit medical-data/data-egress policy approves the target provider and data scope, and it must remain a post-processing step that cannot change the underlying rows.

### 3.11 Audit

Append-only Query Audit Events (`query_audit_events`) record request/execution
metadata for historical reconstruction.

Record at minimum:
- application `audit_id` (correlation across append-only rows)
- actor identity
- timestamp
- active Catalog revision/fingerprint (immutable snapshot ids, no FK cascade)
- Query Template ID/version ids
- Connection Profile id
- parameter names only (`parameter_logging_policy=NAMES_ONLY`)
- sensitive parameter *names* (never values)
- status / event_type
- elapsed time / row count / boolean result truncation indicator
- sanitized `failure_category`

Read API: `GET /api/v1/audit-events` and `GET /api/v1/audit-events/{audit_id}`
(protected by existing `AUDIT_READ`). No public create/update/delete.

`CatalogActivationEvent` and `QueryTemplateReviewEvent` remain separate domain
histories and are not replaced by this table.

Do not log full sensitive result sets, SQL text, request text, credentials,
prompts, or LLM responses.

Durable execution audit (`record_query_audit_event_durable`):
- obtains its own short-lived DQA DB session and commits independently of the
  request-scoped SQLAlchemy transaction (so HTTP errors / rollbacks cannot erase
  the lifecycle)
- reuses the same append-only validation as session-based
  `record_query_audit_event()` (never accepts parameter values, result rows,
  SQL, or secrets)
- production safety gate: if initial `QUERY_REQUEST` / `STARTED` cannot be
  persisted, do **not** execute DEMIS; fail closed with `AUDIT_UNAVAILABLE`
- if final success/failure audit cannot be persisted after a read-only query,
  do not return result rows; return sanitized `AUDIT_UNAVAILABLE`
- session-based writer remains available for internal/tests

## 4. Initial technology choices

Backend:
- FastAPI
- Python 3.11+
- SQLAlchemy
- Pydantic
- pytest

Frontend:
- React
- TypeScript
- Vite

DQA persistence:
- PostgreSQL

Deployment:
- Docker Compose internal/on-premise foundation (`docker-compose.onprem.yml`)
- LAN entry via frontend only (`DQA_LAN_BIND_IP` + `DQA_FRONTEND_PORT`)
- backend and DQA PostgreSQL stay on Compose networks (DB on an internal network; no host DB port)
- production Compose hardcodes `APP_ENV=production` + `DQA_AUTH_PROVIDER=disabled` (fail closed; not `.env`-overridable) until an approved IdP exists
- development auth requires explicit `docker-compose.onprem.dev.yml` overlay
- public DNS / external Traefik optional, not required by the core architecture
- see `docs/runtime-and-deployment.md` for Mode A/B and migration workflow

LLM:
- OpenAI-compatible provider abstraction (`app/adapters/llm`)
- model/provider configured by environment (optional at startup)
- httpx Chat Completions client; structured results via Pydantic validation
- no request/response content logging at the provider boundary

## 5. Data separation

Keep these data classes separate:
1. imported Catalog metadata
2. Query Template authoring/approval state
3. live DEMIS connection configuration
4. live connection profiles / secret references
5. query execution/audit history

Do not mix live DEMIS credentials into imported Catalog records.

## 6. Initial non-goals

Not in the initial implementation:
- DEMIS schema crawling
- arbitrary Text-to-SQL execution
- write queries
- automatic template approval
- automatic Catalog activation for BLOCKED packages
- clinical decision logic
- autonomous agent loops

These can only be reconsidered through explicit design change.


## 7. Production execution gate

The following must exist before any real DEMIS query execution is enabled:

- authentication and role-based authorization
- explicit active Catalog revision
- explicit enabled Connection Profile
- externally verified read-only DB privileges
- approved Query Template version
- deterministic SQL safety validation
- bound parameter validation
- timeout and row limits
- execution audit persistence
- sensitive-parameter logging policy
- LLM data-egress policy (default: no result rows sent to LLM)

Development may implement these components incrementally, but live DEMIS execution must remain disabled until the complete gate is satisfied.
