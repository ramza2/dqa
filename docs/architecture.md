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

### 3.3 Catalog Explorer / Search

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

### 3.4 Query Template Registry

Maintains versioned templates.

Execution eligibility:
- approval_status = APPROVED
- enabled = true
- compatible with active Catalog/source
- SQL passes deterministic safety validation

Templates must be versioned rather than overwritten in place after approval.

### 3.5 Intent / Recommendation

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

### 3.6 Parameter Validation

Validates:
- required fields
- data types
- enum/allowed values
- date/range rules
- maximum list sizes
- source/schema compatibility

Parameters are bound variables, never string-concatenated into SQL.

### 3.7 SQL Safety Gate

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

### 3.8 Read-only DEMIS Adapter

Initial target is Oracle-compatible DEMIS access through a read-only account.

Responsibilities:
- connection lifecycle
- read-only session/transaction where supported
- bound parameter execution
- statement timeout
- result row cap
- normalized result metadata
- sanitized errors

No query generation occurs here.

### 3.9 Result Handling

Return:
- columns
- rows up to allowed limit
- truncation indicator
- elapsed time
- template/version
- active Catalog fingerprint
- audit reference

Optional result summarization by LLM must be a post-processing step and must not change the underlying rows.

### 3.10 Audit

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
- external Traefik
- `.env.production`
- `scripts/deploy.sh`

LLM:
- OpenAI-compatible provider abstraction
- model/provider configured by environment

## 5. Data separation

Keep these data classes separate:
1. imported Catalog metadata
2. Query Template authoring/approval state
3. live DEMIS connection configuration
4. query execution/audit history

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
