# Integrated DQA Platform Architecture

Authoritative **target** architecture for DQA as a DEMIS Data Access & Query
Platform. This document is an architecture rebaseline (Phase 26-B). It does
**not** claim that MCP, Structured Dynamic Query Plan, or Schema Search
integration are already implemented.

Current implementation details remain in [architecture.md](architecture.md).
Operator acceptance for real DEMIS remains in
[real-demis-onboarding.md](real-demis-onboarding.md).

## 1. Product definition

DQA is redefined as:

**DEMIS Data Access & Query Platform**

(not only a natural-language Query Assistant UI).

Primary clients:

1. Human → DQA Web Portal
2. External AI Agent → MCP (SNUH.AI Agent Workflow → MCP → DQA)

Both clients share one Catalog / Authorization / Query Safety / Execution /
Audit Core. They must not grow divergent safety or execution paths.

Product naming:

- Final product / UI / operator docs must **not** use
  `demis-schema-search-poc` as the system name.
- Repository / product identifier `DQA` may remain; the product role follows
  this expanded platform definition.

Existing Approved Query Template capabilities are retained. Future Structured
Dynamic Query Plan is an **additional** path, not a replacement. Arbitrary
LLM-generated SQL direct execution remains forbidden.

## 2. Target architecture

```text
SNUH.AI Agent Workflow
        │
       MCP
        │
        ├──────────────────────┐
        ▼                      │
DQA MCP Interface              │
                               │
DQA Web Portal ────────────────┤
                               ▼
                    Application / Safety Core
                    ├─ Identity / Authorization
                    ├─ Catalog
                    ├─ Data Discovery
                    ├─ Query Planning
                    ├─ Query Policy / Safety
                    ├─ Execution
                    └─ Audit
                               │
                    Read-only DEMIS Adapter
                               │
                             DEMIS
```

Schema metadata side (separate bounded context):

```text
DEMIS Schema Analyzer
        ↓
Catalog Package v2
        ↓
DQA Catalog / Data Discovery
```

DQA does **not** become an unlimited live DEMIS schema crawler. Metadata
acquisition remains Schema Analyzer’s responsibility; DQA consumes packages.

## 3. Bounded contexts

UI consolidation must not merge backend responsibilities.

### Schema Analyzer responsibility

- target DB metadata inspection
- table / column / PK / FK / index / comment collection
- Catalog Package generation
- schema fingerprint generation
- **not** clinical result-data query execution for operators/agents

### DQA responsibility

- Catalog Package validate / import / activate
- Schema / Data Discovery (over activated Catalog)
- Approved Query Template path
- Structured Dynamic Query Plan path (future)
- Authorization
- Read-only execution via dedicated DEMIS adapter
- Audit
- Web Portal
- MCP Tool Provider (future)

## 4. Data Discovery

Capabilities proven in the former Schema Search PoC are **migrated into DQA**
as Data Discovery / Schema Intelligence — not kept as a separate final product.

Implementation note: Phase 27-A search-document contracts exist; Phase 27-B
implements the Data Discovery backend search engine (keyword / semantic /
hybrid, terminology, relation expansion, embedding lifecycle). HTTP/React UI
are Phase 27-C; MCP is Phase 28; Dynamic Query is Phase 29 — none of those are
implemented yet.

Capabilities to promote into DQA:

- Table / Column Explorer
- PK / FK / Index Explorer
- natural-language Schema Search
- Keyword Search
- Semantic Search
- Hybrid Search
- medical terminology expansion
- FK relation expansion
- embedding / index status
- source-scoped search

Development / evaluation-only (may stay separated from core portal UX):

- Gold Set evaluation
- detailed experiment viewer

Migration intent:

- Re-implement / port capabilities into the DQA React Portal and DQA services
- Do **not** integrate the Streamlit UI as-is
- Do **not** copy PoC credential storage; DQA Connection Profile +
  secret-reference boundary remains authoritative
- Do **not** copy PoC deployment topology wholesale

## 5. Query execution paths

### Path A — Approved Query Template (current production path)

```text
Natural language
→ Template Recommendation
→ Parameter Extraction
→ Approved + Enabled Template
→ Preview
→ Explicit Execute
→ DEMIS (read-only)
→ Audit
```

Best for: repetitive, structured, high-stakes, pre-validatable queries.

### Path B — Structured Dynamic Query Plan (future)

For ad-hoc / compound lookups that do not fit a fixed template.

**Critical principle:** Agent/LLM does **not** send executable SQL.

Conceptual plan fields (architecture-level only; no DSL freeze in 26-B):

- resource
- select
- filters
- sort
- group_by
- aggregations
- limit

DQA then applies Catalog mapping, allowlists, binding, authorization, complexity
policy, row limit, timeout, deterministic SQL generation, and read-only
execution. JSON DSL details are deferred to Phase 29 design PRs.

## 6. Dynamic Query safety boundary

Allowed (future Path B):

- approved logical resources
- approved fields
- approved relations
- bounded filters / sort / aggregation
- bounded row limit
- parameterized values only

Forbidden:

- caller-supplied SQL
- LLM-generated SQL direct execution
- arbitrary table/column access
- arbitrary JOIN expression text
- subquery text from caller
- stored procedure/function invocation by caller
- DDL / DML
- caller-controlled DB / credential / profile selection
- unbounded results

Dynamic Query must pass the same gates as Template path:

Authorization → Catalog → Policy / Safety → Read-only Execution → Audit

## 7. Semantic layer

MCP / SNUH.AI contracts should target a **logical resource layer**, not freeze
physical DEMIS schema as the public API.

Example logical resources (illustrative only):

- Patient
- Encounter
- Diagnosis
- Medication
- LabResult
- Procedure

Each maps internally to Active Catalog tables/columns/relations.

**Caution:** Do not implement production Patient/LabResult mappings as
constants before real DEMIS structure is confirmed. Admin Data Discovery UI
may still show physical table/column metadata when needed for operators.

## 8. MCP boundary

Architecture-level tool surface (four tools):

| Tool | Role |
|------|------|
| `demis.search_schema` | NL → candidate resources / fields / relations |
| `demis.describe_resource` | selectable / filterable / sortable fields, relations, capabilities |
| `demis.prepare_query` | prepare Approved Template **or** Structured Dynamic Query Plan; returns READY / NEEDS_CLARIFICATION / BLOCKED; **no DB execute** |
| `demis.execute_query` | execute via safe opaque query token; re-check auth / safety / catalog / profile at execute time |

MCP tools are adapters that call existing DQA application services. They must
not re-implement a parallel safety/execution core.

MCP transport / auth details are future PRs. Do not invent production
IdentityProvider claim formats here.

## 9. Human Web vs MCP

Web (human):

- Query Assistant
- Data Discovery / Schema Explorer
- Template management
- Connection management
- Audit / Readiness operations

MCP (machine):

- SNUH.AI Agent Workflow calls DQA tools

Shared core:

- query preparation
- execution
- authorization
- audit
- catalog
- safety

Forbidden:

- Web-only and MCP-only execute APIs with different safety paths

## 10. Identity propagation

Target concept only (not an approved IdP design):

- Do not trust arbitrary caller-supplied `user_id` / `role` / `permission`
  strings from SNUH.AI as authority
- Future linkage: trusted service authentication + verified end-user
  identity/context
- OIDC / JWT / SSO / claim names deferred until Inframedix / site auth is
  approved
- Distinguish clinical context (`patient_id`, `encounter_id`, …) from
  authorization identity

## 11. Audit

Web and MCP use the same audit core.

Minimum correlation fields (target; no migration in this PR):

- actor
- client type (`WEB` / `MCP`)
- workflow / client request identifier
- query path (`TEMPLATE` / `DYNAMIC`)
- catalog revision
- logical capability / resource
- execution status
- row count
- elapsed time
- failure category

Unchanged policy:

- no result-row persistence
- no parameter-value persistence by default
- no credential / SQL / patient-data logging

## 12. AI services

| Service | Role |
|---------|------|
| LLM | intent, template recommendation, parameter extraction; later structured planning assist |
| Embedding | Schema/Data Discovery semantic retrieval; capability/template retrieval |
| VLM | not required for DQA structured DEMIS query core; may apply in upstream medical AI / document-image ingestion |

AI endpoints / models are configuration concerns. Changes wait for site AI
resource governance and a dedicated configuration PR. Phase 26-B does not
change LLM / Embedding / VLM endpoints.

## 13. Migration strategy from demis-schema-search-poc

Capability migration — **not** a repository merge of the PoC as the product.

1. Contract / model analysis
2. Catalog-compatible Data Discovery model
3. Search engine / service port into DQA boundary
4. Embedding / index lifecycle port
5. DQA APIs
6. React Portal Data Discovery UI
7. Parity comparison vs PoC evidence
8. After DQA validation, treat PoC as reference-only

Do not copy PoC DB credentials, Streamlit app, or deployment layout.

## 14. Non-goals (Phase 26-B)

- runtime code changes
- MCP server implementation
- Dynamic Query compiler
- semantic resource DB model / migrations
- PoC code copy into this repo
- React UI delivery for Discovery
- production IdentityProvider
- real DEMIS endpoints / accounts
- AI endpoint / model configuration changes
- arbitrary SQL execution
- FHIR integration
- SNUH.AI orchestration implementation
