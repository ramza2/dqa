# Security Design

## 1. Security posture

DQA is designed for read-only access to DEMIS-related database information.

Primary principle:
defense in depth; no single control is considered sufficient.

## 2. Trust boundaries

Trust boundaries include:
- browser -> DQA backend
- DQA -> PostgreSQL
- DQA -> LLM provider
- DQA -> DEMIS database
- uploaded Catalog Package -> DQA importer

Each boundary requires validation and sanitized error handling.

A static regression guard scans API route source for common exception-leak
patterns. Route code must not directly stringify typed exceptions, interpolate
their values into public messages, or feed typed-exception state into
`HTTPException.detail`; reviewed public error contracts should be used instead.
Sanitized exception class names used only for readiness diagnostics remain
permitted.

## 3. DEMIS database controls

Required:
- dedicated read-only DB user
- least privilege
- no DML/DDL grants
- connection timeout
- statement timeout
- row/result limit
- bound parameters
- one statement per execution
- read-only transaction/session where DB supports it

Application-side SQL safety validation is additional protection, not a replacement for DB permissions.

A syntactically SELECT statement may still invoke database functions/packages with side effects if the account has execute privileges. The read-only account must therefore also have tightly constrained EXECUTE privileges and least-privilege object grants.

## 4. SQL controls

Execution is allowed only for approved Query Template versions.

Validator must reject at least:
- INSERT/UPDATE/DELETE/MERGE
- CREATE/ALTER/DROP/TRUNCATE
- GRANT/REVOKE
- transaction-control statements
- procedural/anonymous blocks
- multiple statements
- SELECT ... FOR UPDATE
- SELECT ... INTO or equivalent write/locking variants
- unbound user value interpolation

Do not rely on naive substring checks alone in the final validator.
Use a parser/tokenizer appropriate to the supported SQL dialect plus explicit allow rules.
Do not split on raw `";"` — quoted literals and comments must not count as
statement separators. Reject empty/leading/intermediate statements and more
than one trailing terminator.

Execution-path helpers (`require_sql_safe`) must fail closed by raising a typed
error that carries the safety report, not by returning `safe=false` for the
caller to optionally ignore.

Application-side SQL Safety Validator is defense in depth only. It does not
replace the read-only DEMIS account, least-privilege EXECUTE grants, Connection
Profile enablement, RBAC, or audit. A syntactically safe SELECT can still invoke
side-effecting functions/packages when privileges allow; those controls remain
outside the SQL Safety Validator scope.

SQL Safety PASS is independent of Query Template approval/enable flags.
Future execution must require APPROVED + enabled + Active Catalog compatibility
+ SQL Safety PASS + Connection Profile + RBAC + read-only session + audit.

## 5. LLM controls

LLM output is untrusted input.

Never let model output:
- bypass approval
- directly determine executable SQL
- alter runtime permissions
- supply credentials
- change active Catalog state without deterministic authorization

Structured model output must be schema-validated (strict JSON + Pydantic).
Do not auto-repair markdown fences, surrounding prose, or partial JSON.
Do not strip model-specific wrappers such as `<think>` tags; disable thinking
via explicit `LLM_ENABLE_THINKING` when the OpenAI-compatible/vLLM server
requires it.

Provider boundary (`app/adapters/llm`):
- do not log request prompts, message content, or raw provider response bodies
- do not put API keys, Authorization headers, or full request/response bodies
  into exception messages
- sanitize HTTP failures to status-level messages (e.g. "LLM provider returned HTTP 500")
- do not expose a public arbitrary `/chat` proxy
- Recommendation and Parameter Extraction HTTP boundaries allowlist stable
  error codes and static public messages; raw typed-exception messages never
  cross the API boundary
- unknown/unreviewed typed errors fail closed to
  `RECOMMENDATION_INTERNAL_ERROR` or `PARAMETER_EXTRACTION_INTERNAL_ERROR`
  (HTTP 500) with generic static messages
- do not implement query-result summarization or any path that sends result rows
  to an LLM until an approved data-egress policy exists

Template recommendation (`POST /api/v1/query-recommendations`):
- natural-language requests may contain patient identifiers or sensitive values
- raw `request_text` remains local and is never sent to an LLM
- only metadata-derived matched terms and eligible candidate metadata egress
- the recommendation LLM call must pass the central egress policy as
  `TEMPLATE_RECOMMENDATION + METADATA_ONLY`; denial returns
  `RECOMMENDATION_EGRESS_NOT_ALLOWED` (HTTP 403) before any provider call
- do not send SQL text, parameter values, or result rows to the LLM
- do not log raw request text or full prompts
- LLM-returned template IDs must be validated against the deterministic candidate set

Parameter extraction (`POST /api/v1/query-parameters/extract`):
- unlike Recommendation, extraction may need the raw request to recover values
- raw `request_text` egress requires both runtime gates:
  `LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST=true` and
  `LLM_PARAMETER_EXTRACTION_RAW_REQUEST_EGRESS_APPROVED=true`
- when either gate is `false` and the template declares parameters, extraction
  returns `PARAMETER_EXTRACTION_EGRESS_NOT_ALLOWED` (HTTP 403) and does not
  call the LLM provider
- `ALLOW_RAW_REQUEST` is the technical opt-in; `RAW_REQUEST_EGRESS_APPROVED`
  is a runtime assertion that the required external approval exists
- production use still requires an approved provider, network boundary, and
  data-egress policy before enabling both gates
- when enabled, the LLM receives only `request_text`, template/version ids,
  and declared parameter metadata (name, label, description, type, constraints)
- never send SQL text, Catalog-wide metadata, DB credentials, or query result
  rows
- LLM-returned parameter names must be declared on the template; undeclared
  names fail closed (`PARAMETER_EXTRACTION_LLM_OUTPUT_INVALID`)
- do not log `request_text`, resolved values, sensitive values, full prompts,
  or provider raw responses
- responses may contain sensitive resolved values: set
  `Cache-Control: no-store, private` on this endpoint only
- return `sensitive_parameter_names` for UI/audit handling; do not mask values
  in the API body in this phase
- empty parameter schemas skip the LLM even when the egress gate is `false`

Default "do not send patient identifiers to an LLM" remains the standing
policy. Parameter Extraction capability in production requires a separate
explicit data-egress approval beyond flipping the settings flag.

API keys use `SecretStr` and empty keys omit the Authorization header.

## 6. Catalog Package controls

Treat uploaded ZIP as untrusted.

Validate:
- compressed and uncompressed size limits
- file-count / expansion-ratio limits
- safe paths
- package root
- format/version
- manifest checksums
- expected JSON structures

Reject ZIP path traversal and duplicate managed paths.

Catalog Package validation errors expose only reviewed stable codes plus a static
validation message. Unknown/unreviewed validation codes fail closed to
`CATALOG_PACKAGE_INTERNAL_ERROR` (HTTP 500) and do not echo the validation path.

Do not execute or render active content from package artifacts.

## 7. Secret handling

Secrets:
- are provided through environment/secret store
- are not committed
- are not returned by APIs
- are not written to audit logs
- are masked in exceptions

`.env.example` contains placeholders only.

## 8. Medical data and LLM egress

Default policy:
- do not send query result rows to an LLM
- do not send patient identifiers to an LLM
- do not send sensitive medical fields to an LLM
- do not persist full result sets unless an explicit retention requirement exists
- serve result-bearing endpoints only over approved TLS termination
- return no-store/private cache controls for sensitive query results
- do not place result rows or patient identifiers in analytics/telemetry logs

Exceptions must be explicit and reviewed:
- Recommendation never sends raw natural-language request text
- Parameter Extraction may send raw request text only when both
  `LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST=true` and
  `LLM_PARAMETER_EXTRACTION_RAW_REQUEST_EGRESS_APPROVED=true`, and only after
  provider / network / data-egress policy approval for production
- LLM result summarization requires a reviewed data-egress policy covering
  provider, network boundary, permitted fields, redaction/minimization,
  retention, and audit

Keep both Parameter Extraction egress gates disabled (`false`) until that approval exists.

## 9. Audit and privacy

Default audit captures execution metadata, not complete query result data.

Current Query Audit foundation policy:
- audit read API errors use reviewed code/status/static-message contracts;
  unknown typed errors fail closed to `AUDIT_INTERNAL_ERROR` (HTTP 500)
- `parameter_logging_policy = NAMES_ONLY`
- persist parameter names and sensitive parameter names only
- never persist parameter values, hashes of values, SQL, request text, result
  rows, exception bodies, credentials, host/DSN details, prompts, or LLM responses
- `failure_category` is a sanitized bounded token only
- audit identifiers for catalog/template/profile are immutable snapshots without
  FK cascade deletion of history
- read access requires `AUDIT_READ`; no public write API

Future masking/hashing of parameter values remains out of scope until an
explicit retention policy is approved.

Audit retention operational boundaries (see `docs/audit-retention-policy.md`):
- audit events remain append-only during normal application operation
- retention duration is **not** hardcoded (site/project policy not confirmed)
- no public DELETE/PATCH audit API; no automatic purge in this foundation
- any future purge must be offline/privileged, based on `created_at`, and
  recorded externally — never `query_operator` accessible
- operators may inspect aggregates only via `scripts/dqa-audit-retention-status.sh`

DQA PostgreSQL backup/restore (`scripts/dqa-backup.sh` / `scripts/dqa-restore.sh`):
- backs up DQA application DB only (never DEMIS)
- SHA-256 sidecar required for restore; explicit `RESTORE` confirmation token
- refuse restore while backend/frontend are running
- custom-format (`PGDMP`) validated before DROP/CREATE; atomic
  `pg_restore --single-transaction --exit-on-error`
- backup artifacts use restrictive permissions (`umask 077`, dir `0700`, files `0600`)
- relative `DQA_BACKUP_DIR` resolves against repository root (`./backups` ⇒ `<repo>/backups`)
- backups may include Catalog/template/audit operational metadata; store only
  in an approved protected location
- this foundation does not encrypt backups and does not claim external-storage safety
  without an approved encryption policy
- no automatic backup deletion

## 10. Authentication and authorization

Authentication ("who") and authorization ("may this actor do this") are separated.

Identity:
- `IdentityProvider` abstraction returns an `AuthenticatedActor`
- production IdP (OIDC / JWT / SSO) is a future adapter implementing the same interface
- current `dev_headers` provider is for local development/test only
- `X-DQA-Dev-Actor` / `X-DQA-Dev-Roles` are identity assertions, not security
  credentials, and must never be trusted as production headers

Config:
- `DQA_AUTH_PROVIDER` default `disabled` (fail-closed on protected endpoints: 503)
- `dev_headers` is allowed only when `APP_ENV` is `development` or `test`
- enabling `dev_headers` under production fails closed (503)
- on-prem production Compose (`docker-compose.onprem.yml`) **hardcodes**
  `APP_ENV=production` and `DQA_AUTH_PROVIDER=disabled` (not overridable via `.env.onprem`)
- development auth requires the explicit `docker-compose.onprem.dev.yml` overlay
  (`APP_ENV=development`, `DQA_AUTH_PROVIDER=dev_headers`) — never production
- production SPA builds must never inject `VITE_DQA_DEV_ACTOR` / `VITE_DQA_DEV_ROLES`

HTTP mapping:
- unauthenticated / invalid identity → 401
- authenticated without permission → 403
- provider disabled / unavailable → 503

Roles: `viewer`, `template_author`, `template_approver`, `query_operator`,
`auditor`, `administrator`.

Permissions are resolved from roles; routes check permissions only.
Unknown roles fail closed. LLM output never determines actor, role, or permission.

Protected in this foundation:
- Query Template registry / approval / review-event read
- Template Recommendation
- Parameter Extraction
- Connection Profile management (`CONNECTION_PROFILE_MANAGE`, administrator only)
- Catalog read (`CATALOG_READ`): active Catalog pointers/metadata query,
  import history, activation history
- Catalog management (`CATALOG_MANAGE`, administrator only): package validate,
  package import, revision activation
- Execution preview (`QUERY_OPERATE`; no DEMIS connection / no credential resolve)
- Query execution form metadata (`QUERY_OPERATE`; parameter/environment projection
  without `TEMPLATE_READ` or `CONNECTION_PROFILE_MANAGE`)
- Query execution (`QUERY_OPERATE`; durable audit; fail closed without concrete adapter)

`query_operator` receives `CATALOG_READ` so Query Assistant can discover active
Catalog sources without gaining package validate/import/activate rights.

Connection Profile rules:
- credentials are referenced, never stored as secret values
- diagnostics are configuration-level only (no live DEMIS connection test)
- Catalog activation does not auto-create or mutate Connection Profiles
- Connection Profile, Catalog activation/query, and Query Template HTTP
  boundaries use reviewed code/status/static-message contracts; typed exception
  messages never cross the public API boundary
- unknown/unreviewed domain error codes fail closed to domain-specific
  `*_INTERNAL_ERROR` codes (HTTP 500)

Execution preview rules:
- public eligibility/form errors use reviewed code/status/static-message
  contracts; unknown typed errors fail closed to
  `EXECUTION_PREVIEW_INTERNAL_ERROR` (HTTP 500)
- authoritative catalog/profile/template metadata loaded server-side only
- resolved parameter values may appear in the preview response for confirmation
  (`Cache-Control: no-store, private`); never log or persist parameter values
- SQL text, host/port/username/database, credential refs, and DSN never returned
- live execution remains blocked (`execution_available=false`,
  `DEMIS_ADAPTER_UNAVAILABLE`) until a concrete DEMIS adapter exists
- preview does not write audit events

Query execution rules:
- orchestration errors use reviewed code/status/static-message contracts;
  unknown typed errors fail closed to `QUERY_EXECUTION_INTERNAL_ERROR` (HTTP 500)
- DEMIS adapter errors use the same shared public-error mapper while preserving
  the existing fail-closed fallback to `DEMIS_EXECUTION_FAILED` (HTTP 502)
- same caller-controlled fields as preview; never accept caller SQL, catalog
  revision/fingerprint, connection_profile_id, row_limit, timeout, actor/audit
  metadata, or credentials
- always re-runs `evaluate_execution_eligibility()`; never trusts a prior preview
- durable audit lifecycle (`QUERY_REQUEST` / `QUERY_EXECUTION` ×
  STARTED|SUCCEEDED|DENIED|FAILED) commits on an independent DQA session
- parameter audit is NAMES_ONLY (plus sensitive names); never values
- result rows are never logged, persisted, exception-embedded, or LLM-egressed
- if initial STARTED audit cannot persist → `AUDIT_UNAVAILABLE` (503), no DEMIS call
- if final success audit cannot persist → `AUDIT_UNAVAILABLE` (503), no rows returned
- production path cannot select fake adapters; live DEMIS remains unavailable until
  a concrete DBMS adapter exists (`DEMIS_ADAPTER_UNAVAILABLE` before credentials)

Execution form metadata rules:
- `GET /api/v1/query-executions/form` is a QUERY_OPERATE-only projection for
  parameter forms and environment selection
- does not grant template registry read or Connection Profile management
- returns parameter schema metadata (including defaults/sensitive flags) without
  runtime parameter values or SQL text
- exposes only enabled environments; never host/user/db/credential refs/profile ids

Not yet covered (follow-up):
- OIDC/OAuth2/JWT verification, user directory, MFA, sessions
- concrete DEMIS DBMS driver / live connectivity (Oracle thin adapter is
  registered; live mock/network/secret wiring remains operator-side)
- production credential secret-store resolver (beyond env-prefix boundary)
- production IdentityProvider (Catalog RBAC closes authorization gaps only)
## 11. Production checklist

Before real DEMIS access:
- read-only account verified
- no write privileges
- TLS/network controls confirmed
- secret storage approved
- query timeout tested
- row limits tested
- unsafe SQL rejection tested
- audit retention defined
- authentication/RBAC enabled
- Connection Profile binding/authorization defined
- execution audit persistence enabled before live queries
- package import/activation authorization defined
- LLM result-data egress disabled unless explicitly approved
- concrete DEMIS read-only adapter selected only after DBMS/driver requirements are confirmed
  (Oracle thin adapter is now registered; live wiring remains operator-side)

## 12. DEMIS read-only adapter boundary

Foundation (`app/adapters/demis`):
- DBMS-neutral protocol/DTOs plus production-selectable Oracle thin adapter
- DQA PostgreSQL/`psycopg` must never be used as the DEMIS adapter
- fake/test adapters are test-only and cannot be selected by the production factory
- first production credential source: `EnvironmentCredentialResolver` (`env:` only)
  with dedicated prefix `DQA_DEMIS_CREDENTIAL_ENV_PREFIX` (default `DEMIS_SECRET_`)
- arbitrary process environment variables (PATH, HOME, DQA_DB_PASSWORD, cloud keys)
  cannot be resolved through this boundary
- future approved secret stores may implement the same `CredentialResolver` protocol
- credential values, host/port/username/database, DSN, credential refs, and result
  rows must never appear in logs, exceptions, or public API payloads
- the query-execution HTTP boundary allowlists DEMIS adapter error codes and uses
  static public messages; unknown adapter codes are normalized to
  `EXECUTION_FAILED` instead of echoing raw adapter code/message text
- adapter assumes SQL Safety already passed and must not weaken it
- DB least privilege remains mandatory outside application controls
- Connection Profile diagnostics remain configuration-level until a concrete
  adapter sets `live_connection_tested` after an explicit probe
- Oracle adapter registration does not by itself prove live DEMIS connectivity

## 13. On-prem deployment exposure

Production Compose foundation (`docker-compose.onprem.yml`):
- frontend is the only LAN-facing service
- backend listens on the Compose network only (not published to host/LAN)
- DQA PostgreSQL has no host port; attached to an internal Compose network
- `APP_ENV=production` and `DQA_AUTH_PROVIDER=disabled` are hardcoded in Compose
  (`.env.onprem` cannot enable development auth)
- development auth is opt-in only via `docker-compose.onprem.dev.yml`
- no DEMIS fake adapter selection, no Traefik by default
- do not expose `5432` or `8000` on `0.0.0.0`
- real `.env.onprem` is gitignored; only `.env.onprem.example` is committed
- `DQA_DB_PASSWORD` must be supplied explicitly (no weak Compose default)
- `dqa-up.sh` refuses to start backend until Alembic revisions are at head

## 14. Runtime edge hardening (Phase 1)

Frontend nginx is an outer resource/attack-surface boundary only:

- general `/api/` `client_max_body_size 2m`
- Catalog `validate` / `import` raised to `55m` (backend archive limit remains 50 MiB)
- explicit proxy/client send/read/header/body timeouts (not unlimited)
- backend SQL/query timeouts remain authoritative
- CSP + Permissions-Policy + nosniff / DENY frame / no-referrer
- no HSTS here — TLS/HSTS belong at the approved TLS termination point
- hashed `/assets/` immutable cache; `index.html` no-cache; no `proxy_cache`
- `server_tokens off`; no X-DQA-Dev-* injection

Production FastAPI docs exposure:
- `APP_ENV=production` disables `/docs`, `/redoc`, `/openapi.json`
- development/test keep docs
- this is attack-surface reduction, not authentication

Request-bound review (Phase 1):
- recommendation / parameter extraction request text already length-bounded
- execution preview/execute parameter maps bounded
- connection profile mutation fields length-bounded
- query template create/update/new-version text and list fields length-bounded
- Catalog upload remains bounded by backend `max_archive_bytes`

Query execution limits (authoritative):
- each approved Query Template defines `row_limit` and `timeout_seconds`
- application hard maximums are currently `timeout_seconds <= 300` and
  `row_limit <= 10_000` (`app.adapters.demis.types.MAX_TIMEOUT_SECONDS` /
  `MAX_ROW_LIMIT`)
- execution eligibility validates these limits server-side
- do not advertise unused `QUERY_DEFAULT_*` / `QUERY_MAX_*` environment knobs;
  site-wide tighter limits require an explicit future policy feature

Rate limiting:
- deferred pending confirmed internal concurrency / traffic profile
- future policy should distinguish inexpensive reads, Catalog manage uploads,
  LLM-backed endpoints, and query preview/execute

Outstanding blockers outside this repository change:
1. approved production IdentityProvider
2. confirmed DEMIS DBMS / driver requirements
3. approved TLS termination for real medical-data use
4. approved audit/backup retention duration and storage/encryption policy
