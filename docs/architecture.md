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

### 3.3 Connection Profile

A Connection Profile is separate from imported Catalog metadata.

Responsibilities:
- bind a logical Catalog source/environment to one live DEMIS target
- reference credentials through environment/secret management rather than Catalog data
- store non-secret compatibility metadata
- expose sanitized connection diagnostics
- support explicit enable/disable state

Activation of a Catalog revision does not automatically create or modify a live connection profile.

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

### 3.5 Query Template Registry

Maintains versioned templates.

Execution eligibility:
- approval_status = APPROVED
- enabled = true
- compatible with active Catalog/source
- SQL passes deterministic safety validation

Templates must be versioned rather than overwritten in place after approval.

### 3.6 Intent / Recommendation

Input:
- natural-language user request
- active Catalog metadata
- approved Query Templates

Output:
- recommended template IDs
- confidence/reason
- extracted candidate parameters
- clarification requirement when information is insufficient

The LLM is advisory. The backend performs final deterministic validation.

### 3.7 Parameter Validation

Validates:
- required fields
- data types
- enum/allowed values
- date/range rules
- maximum list sizes
- source/schema compatibility

Parameters are bound variables, never string-concatenated into SQL.

### 3.8 SQL Safety Gate

Central deterministic component.

Minimum checks:
- single statement
- SELECT-only
- no DML/DDL/TCL/DCL
- no procedural block
- no unapproved template
- row/timeout limits
- parameters match declared definitions

The safety gate runs even for approved templates.

### 3.9 Read-only DEMIS Adapter

The adapter interface is DBMS-neutral.
The first concrete DBMS implementation must be selected after the actual DEMIS connection requirements are confirmed.

Responsibilities:
- connection lifecycle
- read-only session/transaction where supported
- bound parameter execution
- statement timeout
- result row cap
- normalized result metadata
- sanitized errors

No query generation occurs here.

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

Record at minimum:
- request/audit ID
- actor identity when authentication is introduced
- timestamp
- active Catalog revision/fingerprint
- Query Template ID/version
- parameter names and safe values according to policy
- execution target
- status
- elapsed time
- row count
- failure category

Do not log full sensitive result sets by default.

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
- Docker Compose
- direct LAN IP + explicit ports for internal/on-premise operation
- DQA PostgreSQL kept internal or loopback-only
- public DNS / external Traefik optional, not required by the core architecture

LLM:
- OpenAI-compatible provider abstraction
- model/provider configured by environment

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
