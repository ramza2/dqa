# AGENTS.md

# DEMIS Query Assistant (DQA)

## 1. Purpose

DQA is the **target single deployable DEMIS Schema Intelligence, Data Access and
MCP Tool Platform**. The independent `demis-schema-search-poc` is a reference
implementation and temporary parity baseline, **not a final production dependency**.

**Currently implemented:** DQA consumes validated Catalog Package v2, supports
Catalog/Data Discovery and approved Query Template **read-only** DEMIS execution,
and has an internally restricted MCP surface. The independent Schema Analyzer
still performs schema inspection in the existing deployment.

**Planned in separately reviewed implementation PRs:** an internal Oracle
**metadata-only Schema Inspector**; Catalog snapshot/package generation and
diff/activation integration; approved client-facing DEMIS MCP/REST operations;
a **separate, default-disabled controlled clinical Insert** path subject to
institutional approvals. Do not represent planned features as implemented.

See `docs/integrated-platform-architecture.md` and `docs/roadmap.md`.
The single-clinician-UI/approval-verification clarification is in PR #66
until that PR is merged; avoid depending on unmerged changes as runtime policy.

## 2. Core boundary

Target responsibilities within DQA (separate service/adapter boundaries):
- **Schema Inspector:** explicit, authorized read-only Oracle *metadata* queries;
  no clinical/business-row retrieval, no changes to DEMIS, no arbitrary SQL.
- **Catalog ingestion:** validates internally generated or externally supplied
  Catalog Package v2 using the **same** established schema/manifest checks.
  Import persists immutable revisions; activation is explicit and READY-only.
- **Read Query Core:** approved + enabled Query Templates, read-only connection
  and SQL-safety gates, bounded execution with durable audit. Current adapter
  remains strictly SELECT-only.
- **Future Controlled Write Core:** distinct operation registry, write credentials,
  clinical approval evidence verification, idempotency and execution audit;
  **not implemented and not permitted by these documentation edits**.
- **External orchestration:** SNUH.AI clinician UI/workflow; the FHIR service
  standardizes DEMIS/PACS/other sources. DQA does not replace the clinician UI
  or implement its own clinical approval/rejection screen.

Supported Catalog Package:
- `package_format: demis-catalog-package`
- `package_version: 2.x`

Do not copy the PoC's database, secret persistence, Streamlit UI or its v1
package writer into DQA wholesale. Reuse only reviewed metadata inspection
logic and generate **v2-compatible** packages via the DQA validation path.
Keep the existing external Package Import path available for offline transfer,
backup/recovery and compatibility.

Do not hard-code mock DEMIS schema knowledge into production logic.
The current Oracle mock schema is development/test data only.

## 3. Source of truth

The **active, validated, immutable Catalog revision** remains authoritative
for runtime discovery and read execution even after DQA gains direct inspection.
A newly collected Snapshot is **not** execution authority until it passes the
same v2 validation, is persisted as a new revision and explicitly activated.
The activated Catalog Package is authoritative for:
- schema
- tables
- columns
- PK / UK
- FK
- indexes
- DB comments
- categories
- physical schema snapshot
- schema fingerprint
- package validation/readiness metadata

Never invent tables, columns, relationships, comments, or medical meaning that are not supported by the active package.

## 4. Package import rules

Every package must be validated before activation.

Validate at minimum:
1. ZIP structure and root
2. package_format
3. package_version compatibility
4. manifest file list
5. SHA-256 for each manifest-managed file
6. source identity
7. schema fingerprint
8. package readiness
9. JSON parseability and required fields

Activation policy for the initial implementation:
- READY: may be activated
- WARNING: may be imported for inspection but must not be activated for query execution
- BLOCKED: must not be activated

Any future WARNING override requires an explicit reviewed design change and audit policy.

Never silently repair, rewrite, or partially accept a corrupt package.

## 5. Query execution safety

**Current runtime is strictly read-only.** Existing query APIs/MCP Tools,
`OracleReadOnlyDemisAdapter`, approved Query Templates, SQL Safety Validator,
and Oracle read account must **never** execute writes.

For the current execution path, reject executable:
- INSERT / UPDATE / DELETE / MERGE / UPSERT
- CREATE / ALTER / DROP / TRUNCATE / GRANT / REVOKE
- procedural/anonymous blocks and arbitrary DDL/DML
- multi-statement execution

**Future exception is a new, separate Controlled Write subsystem only**
(and not an exception to read-path checks): it may eventually support
**specifically approved clinical-record Insert operations** only, using the
site-authorized official storage API/procedure when available or a specifically
authorized narrow DB Insert mechanism. It is **not allowed to execute now**.
No user/LLM-authored SQL, generic Insert/CRUD, UPDATE/DELETE/MERGE, or clinical
auto-approval is permitted. Do not implement the new subsystem until the
operation/field scope, hospital approvals, integration method, DB privileges,
approved design, security tests and explicit implementation PR are in place.

The clinical reviewer approves **once** through SNUH.AI or the military's
approved workflow. DQA must *independently verify* authenticated approval
evidence bound to the exact document hash/version, patient/Encounter, approver
authority, operation, expiration/revocation and trusted source immediately
before commit. DQA has **no clinician approval UI**; automatic verification
is not a second approval. Approval-original audit belongs to the approval
system; DQA stores minimal write/execution audit and correlation IDs.

Write preparation must never modify DEMIS. Write commit, if later authorized,
requires a distinct write permission, secret/adapter, allowlisted operation,
fail-closed audit, idempotency, durable result status and reconciliation of
ambiguous commits **before** any replay. Disable all write capabilities by
default; use synthetic/mock data for development until separate site signoff.

The LLM must never directly generate SQL that is immediately executed.

Allowed runtime path:

Natural language request
-> active Catalog retrieval
-> approved Query Template recommendation
-> parameter extraction
-> type/constraint validation
-> SQL safety validation
-> preview
-> approved read-only execution
-> result handling
-> audit log

**Existing read-path executable SQL** must originate from an APPROVED and
ENABLED Query Template; the Structured Dynamic Query compiler remains
preview-only until a separate reviewed read-execution safety gate.
Future Controlled Write operations do **not** use read Query Templates,
read execution tokens or caller-supplied SQL.

Defense in depth:
- read-only DEMIS account
- SELECT-only SQL validation
- one statement only
- bound parameters
- statement timeout
- maximum row limit
- database read-only session/transaction where supported
- result-size controls
- audit logging

## 6. Query Template rules

Query Templates are managed first-class objects.

A template should contain at least:
- template_id
- name
- description
- source/catalog compatibility
- target schemas
- SQL template
- parameter definitions
- parameter types
- required/optional rules
- allowed value constraints when applicable
- maximum row count
- timeout
- enabled flag
- approval status
- version
- created_at
- updated_at
- approval/audit metadata

Only APPROVED + ENABLED templates may be executed.

LLM/search may recommend a template but cannot bypass approval.

## 7. LLM responsibilities

The LLM may:
- interpret user intent
- retrieve relevant catalog objects
- rank approved Query Templates
- extract parameters
- explain catalog metadata
- summarize query results only when an approved data-egress policy explicitly permits it

The LLM must not:
- execute arbitrary generated SQL
- fabricate schema facts
- fabricate unsupported medical meaning
- bypass Query Template approval
- expose credentials or infrastructure secrets
- change the active Catalog Package

Use a provider abstraction for all LLM calls.
Do not bind domain code to one model vendor.

By default, query result rows, patient identifiers, and other sensitive medical data must not be sent to an LLM.
Result summarization is disabled until an explicit provider/data-egress policy is approved and implemented.

## 8. Security

Never commit, log, return, or embed:
- database passwords
- encrypted credentials
- API keys
- access tokens
- private certificates
- production host secrets

Secrets come from environment variables or an approved secret store.

Mask secrets and connection details in errors.

Audit metadata should be sufficient to reconstruct:
- who requested execution
- which active catalog version was used
- which template/version was selected
- which parameter names were used
- execution timing/status
- row count
- failure category

Do not log sensitive result rows by default.

## 9. Architecture

Recommended backend layering:

API
-> application/service
-> domain
-> repository/adapter
-> external DB / LLM / persistence

Rules:
- keep FastAPI routes thin
- keep SQL safety logic outside route handlers
- keep existing DEMIS **read execution** behind its dedicated read-only adapter;
  introduce any future authorized metadata-only Inspector and Controlled Write
  adapter through separately gated services, accounts and audit policies
- keep Catalog Package parsing independent of live DB connectivity
- keep LLM provider access behind an interface
- keep import/activation separate from query runtime

## 10. Development workflow

Before coding:
1. read this file and relevant nested AGENTS.md files
2. inspect existing implementation patterns
3. state the minimal implementation plan
4. avoid unrelated refactoring

For feature work:
- create a feature branch
- use focused commits
- add/update tests
- run focused tests first
- run relevant regression tests
- report runtime validation separately
- open a PR
- do not merge automatically

Do not delete working functionality merely to simplify a change.
Prefer backward-compatible changes unless explicitly instructed otherwise.

## 11. Git / PR policy

Never push feature work directly to main.

Never merge a PR without explicit user approval.

Before asking for merge approval, report:
- branch
- PR number
- changed scope
- tests run and results
- deployment/runtime validation
- known limitations or follow-up items

## 12. Deployment target

Initial deployment pattern for development, internal testing, and expected on-premise operation:
- Docker Compose
- direct LAN IP + explicit host ports
- no public DNS requirement
- no Traefik requirement
- application ports exposed only on the configured trusted LAN interface
- DQA PostgreSQL kept loopback/internal-only unless explicitly required

External Traefik/DNS routing is optional and must only be added when an explicitly public or shared external deployment is required.

When implemented, the internal deployment script should:
- validate required environment variables
- require/print the selected LAN bind IP
- validate Compose configuration
- build required images
- deploy with `--remove-orphans`
- wait for backend/frontend health
- print LAN access URLs and service status

Do not expose database ports broadly to the LAN or Internet.
Do not assume Traefik is present in an on-premise installation.

## 13. Testing expectations

Backend behavior changes require pytest coverage.

At minimum test:
- success path
- invalid input
- unknown resource
- security boundary
- approval boundary
- package tamper detection where relevant
- SQL rejection paths for unsafe statements

Package import tests must verify checksums and reject tampered files.

Do not claim work complete based on static inspection only.

## 14. Implementation sequence

The items below are **historical bootstrap order**, not the current
post-Phase-29 task list. Current priority and gates are maintained in
`docs/roadmap.md` (U-03 → U-02/S-01 Inspector → parity → read/MCP ICD →
controlled-write planning/acceptance). Do not interpret this historical list
as authorization to skip gates.

Historical implementation order:

1. bootstrap/project structure
2. Catalog Package v2 import and validation
3. active Catalog management
4. Catalog/Table/Column explorer and search
5. Query Template registry
6. Query Template approval/versioning
7. natural language -> Query Template recommendation
8. parameter extraction and validation
9. read-only DEMIS adapter
10. execution preview and read-only query execution
11. result presentation
12. audit log
13. deployment and operational hardening

Do not jump directly to arbitrary LLM-generated SQL execution.
