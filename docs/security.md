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

Structured model output must be schema-validated.

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

LLM result summarization requires a reviewed data-egress policy covering provider, network boundary, permitted fields, redaction/minimization, retention, and audit.

## 9. Audit and privacy

Default audit should capture execution metadata, not complete query result data.

Parameter logging policy should distinguish:
- safe operational parameter
- sensitive medical/patient identifier
- secret

Sensitive parameter values should be masked or hashed according to future operational requirements.

## 10. Authentication and authorization

Authentication/RBAC is not implemented in bootstrap.

Before production use, define roles such as:
- viewer
- template_author
- template_approver
- query_operator
- auditor
- administrator

Template author and approver separation should be supported where required.

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
