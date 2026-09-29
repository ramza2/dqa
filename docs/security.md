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
- do not implement query-result summarization or any path that sends result rows
  to an LLM until an approved data-egress policy exists

Template recommendation (`POST /api/v1/query-recommendations`):
- natural-language requests may contain patient identifiers or sensitive values
- raw `request_text` remains local and is never sent to an LLM
- only metadata-derived matched terms and eligible candidate metadata egress
- do not send SQL text, parameter values, or result rows to the LLM
- do not log raw request text or full prompts
- LLM-returned template IDs must be validated against the deterministic candidate set

Parameter extraction (`POST /api/v1/query-parameters/extract`):
- unlike Recommendation, extraction may need the raw request to recover values
- raw `request_text` egress is gated by
  `LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST` (default `false`)
- when the gate is `false` and the template declares parameters, extraction
  returns `PARAMETER_EXTRACTION_EGRESS_NOT_ALLOWED` (HTTP 403) and does not
  call the LLM provider
- setting the gate to `true` is a technical opt-in only; it does **not**
  constitute production medical/data-egress approval
- production use still requires an approved provider, network boundary, and
  data-egress policy before enabling the gate
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
- Parameter Extraction may send raw request text only behind
  `LLM_PARAMETER_EXTRACTION_ALLOW_RAW_REQUEST=true`, and only after provider /
  network / data-egress policy approval for production
- LLM result summarization requires a reviewed data-egress policy covering
  provider, network boundary, permitted fields, redaction/minimization,
  retention, and audit

Keep Parameter Extraction disabled (`false`) until that approval exists.

## 9. Audit and privacy

Default audit captures execution metadata, not complete query result data.

Current Query Audit foundation policy:
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
- Execution preview (`QUERY_OPERATE`; no DEMIS connection / no credential resolve)

Connection Profile rules:
- credentials are referenced, never stored as secret values
- diagnostics are configuration-level only (no live DEMIS connection test)
- Catalog activation does not auto-create or mutate Connection Profiles

Execution preview rules:
- authoritative catalog/profile/template metadata loaded server-side only
- resolved parameter values may appear in the preview response for confirmation
  (`Cache-Control: no-store, private`); never log or persist parameter values
- SQL text, host/port/username/database, credential refs, and DSN never returned
- live execution remains blocked (`execution_available=false`,
  `DEMIS_ADAPTER_UNAVAILABLE`) until a concrete DEMIS adapter exists
- preview does not write audit events

Not yet covered (follow-up):
- Catalog Package import / activation admin authorization
- Catalog Explorer admin surfaces
- OIDC/OAuth2/JWT verification, user directory, MFA, sessions
- public execute endpoint + audit writes for QUERY_REQUEST / QUERY_EXECUTION
- concrete DEMIS DBMS driver / live connectivity (blocked on confirmed requirements)
- production credential secret-store resolver

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

## 12. DEMIS read-only adapter boundary

Foundation (`app/adapters/demis`):
- DBMS-neutral protocol and DTOs only; no concrete DEMIS driver package
- DQA PostgreSQL/`psycopg` must never be used as the DEMIS adapter
- fake/test adapters are test-only and cannot be selected by the production factory
- first production credential source: `EnvironmentCredentialResolver` (`env:` only)
  with dedicated prefix `DQA_DEMIS_CREDENTIAL_ENV_PREFIX` (default `DEMIS_SECRET_`)
- arbitrary process environment variables (PATH, HOME, DQA_DB_PASSWORD, cloud keys)
  cannot be resolved through this boundary
- future approved secret stores may implement the same `CredentialResolver` protocol
- credential values, host/port/username/database, DSN, credential refs, and result
  rows must never appear in logs, exceptions, or public API payloads
- adapter assumes SQL Safety already passed and must not weaken it
- DB least privilege remains mandatory outside application controls
- Connection Profile diagnostics remain configuration-level until a concrete
  adapter can set `live_connection_tested`
- concrete DEMIS DBMS adapter remains unavailable until requirements are confirmed
