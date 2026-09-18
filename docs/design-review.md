# Bootstrap Design Review

Date: 2026-09-18

This review checks the bootstrap design before implementation begins.

## 1. Result

Status: READY FOR IMPLEMENTATION

The bootstrap architecture is suitable for beginning the roadmap with the backend application skeleton.

No business/query execution code exists in the bootstrap PR.

## 2. Decisions confirmed

### 2.1 Schema Analyzer / DQA boundary

Confirmed:
- Schema Analyzer produces Catalog Package v2.
- DQA consumes validated packages.
- DQA does not duplicate schema crawling or physical metadata inspection.

Reason:
Keeping producer and consumer responsibilities separate prevents DQA from silently deriving a different schema truth than the Analyzer.

### 2.2 Catalog activation policy

Initial policy:
- READY -> activation allowed
- WARNING -> import/inspection only
- BLOCKED -> diagnostics only

WARNING activation is intentionally not supported initially.

### 2.3 Connection Profile separation

Live DEMIS connectivity is not part of the Catalog Package.

DQA will use a separately managed Connection Profile to bind:
- Catalog source/environment
- live DEMIS target
- non-secret connection metadata
- secret references

Catalog activation must not automatically alter live connection configuration.

### 2.4 No arbitrary Text-to-SQL execution

Confirmed execution path:

```text
Natural language
-> Catalog retrieval
-> approved/enabled Query Template
-> parameter extraction
-> deterministic validation
-> preview
-> explicit execute action
-> read-only DB adapter
-> audit
```

The LLM is advisory and is not a security boundary.

### 2.5 DBMS assumption

The bootstrap must not assume the real DEMIS DBMS is Oracle.

The adapter interface remains DBMS-neutral.
A concrete implementation is selected only after actual DEMIS integration requirements are confirmed.

### 2.6 Production execution prerequisites

Real DEMIS execution must not be enabled before all of these exist:
- authentication/RBAC
- active READY Catalog
- enabled compatible Connection Profile
- verified read-only DB privileges
- approved/enabled Query Template version
- deterministic SQL and parameter validation
- timeout / row limit
- persistent execution audit

The roadmap was reordered so these prerequisites precede live execution.

### 2.7 Medical data / LLM boundary

Default:
- query result rows are not sent to an LLM
- patient identifiers are not sent to an LLM
- sensitive medical fields are not sent to an LLM

Any future result summarization requires a reviewed data-egress policy.

### 2.8 SQL read-only limitations

Application validation rejects write/locking forms such as:
- DML / DDL / privilege / transaction control
- multiple statements
- SELECT ... FOR UPDATE
- SELECT ... INTO or equivalent forms

However, SQL syntax validation alone is not sufficient because a SELECT can invoke functions with side effects when permissions allow it.

Therefore DB-level least privilege and restricted EXECUTE grants remain mandatory.

### 2.9 Catalog Package archive safety

Package import must defend against:
- checksum tampering
- path traversal
- duplicate entries
- unmanaged entries
- symlink-like/non-regular entries
- excessive file count
- excessive uncompressed size
- zip-bomb expansion

Imported revisions remain immutable.

### 2.10 Sensitive result delivery

For query results:
- approved TLS termination is required
- sensitive result responses should use no-store/private cache policy
- result rows/patient identifiers must not enter analytics or telemetry logs
- full result persistence is disabled unless explicitly required

## 3. Over-constraint review

The design intentionally does not require:
- arbitrary SQL generation
- semantic/vector search from day one
- one specific DEMIS DBMS
- LLM result summarization
- autonomous agent behavior

These remain optional future capabilities and should not block the initial implementation.

## 4. Implementation starting point

The next implementation scope remains:

`docs/roadmap.md -> PR 2 - Backend application skeleton`

It should not implement:
- Catalog import
- Query Template management
- LLM calls
- live DEMIS DB connection
- query execution

This keeps the first Cursor implementation small and reviewable.
