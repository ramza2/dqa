# DQA Architecture Decision — CPU-first / Model-Optional Deployment

Status: **proposed internal design decision**, 2026-10-23. DQA is not presumed to be adopted in the official consortium architecture. This decision supersedes the *mandatory LLM-based Query Template creation* assumption in the initial U-01-R2 plan; the final implementation still requires testing and approval.

## 1. Constraint

The military site may not permit DQA to access the model served to SNUH.AI, and may not approve installing a separate generative LLM on the H200×8 host. DQA therefore **MUST operate end-to-end without any generative LLM**. It must not allocate GPU resources, create a second vLLM deployment, or depend on a remote commercial API as a hidden fallback.

Even installing a **CPU embedding model** may require security/software approvals. To stay functional in that case, the **zero-model keyword/manual path** is mandatory. CPU embedding is an optional enhancement, not a gate for schema analysis, authoring, approval, execution, or MCP use.

## 2. Operating modes

| Mode | External/installed model dependency | Product behavior | Mandatory? |
| --- | --- | --- | --- |
| A. **Zero-model baseline** | None | Oracle metadata Inspector/Snapshot/Catalog, SQL/Template editor, safe graphical structured SELECT authoring (whitelisted fields/joins/filters), keyword/FTS/terminology matching, deterministic template recommendations, explicitly entered/validated parameters, preview, approved read-only SELECT, audit, MCP | **Yes** |
| B. **CPU embedding enhancement** | Site-approved small embedding runtime/model using CPUs only; no GPU claim | Semantic/Hybrid Catalog and Template retrieval. Still cannot create arbitrary SQL or reliably extract parameter values without constrained rules | Optional |
| C. **Generative LLM assist** | **Separate explicit** model/API/use/security approval; access to SNUH.AI model **never assumed** | Natural language → Query Template DRAFT proposal and optional reranking/parameter suggestions. Always reviewed, SQL checked and manually approved before any executable action | Deferred |

Embedding model **does not generate SQL**. Semantic search/recommendation ≠ natural-language-to-SQL generation. DQA will never silently promote/reinterpret generated query text as authorized SQL.

## 3. Actual repository gap at main@6e3f135

- `data_discovery_search/service.py`: keyword works with PostgreSQL search only; semantic/hybrid requires a configured embedding provider.
- `adapters/embedding/factory.py`: only OpenAI-compatible **HTTP** embedding provider exists; no in-process CPU-only adapter and **no CPU performance/packaging evaluation yet**. Any candidate (e.g., BGE-M3) needs runtime, version, model revision, dimensionality and resource measurements; existing pgvector embedding dimension=1024.
- `template_recommendation.py`: deterministic lexical *candidate scoring* exists, but `_rank_with_llm` is still mandatory on a matching candidate and may fail due LLM egress policy/provider absence. There is **no successful full no-LLM recommendation path** yet. Implement deterministic confidence/clarification and threshold gates before declaring Mode A ready.
- `parameter_extraction.py`: nonempty parameter schemas require the LLM egress path; no-LLM fallback must show **explicit parameter form**, typed/default value validation and clarification. Do not guess patient/encounter identifiers from loose natural language.
- `query_compiler.py`: deterministic Oracle SELECT compiler exists, outputs **preview-only**, requires validated StructuredQueryPlan and Semantic Resource mappings. It must not be treated as an already-connected UI authoring or executable/template approval system.
- `mcp/server.py` + Adapter: existing discovery/approved-template prepare/execute tools do not inherently require generative LLM; semantic search does require configured embeddings. No external connectivity presumed.

## 4. Updated M0–M6 milestones and acceptance

- **M0:** record Oracle Mock running/healthy and source checkout. Existing `database/free:latest-lite` is **not evidence of Oracle 19c**. Site DEMIS 19c is a user-provided deployment fact; replica DB version remains unknown.
- **M1:** development-gated Oracle Mock Target prepare/explicit read-only probe/enable UI. Draft PR #134 code review: backend **18 passed**, frontend **12 passed**, build + lint PASS, `M1_CODE_REVIEW_PASS` from user's 2026-10-23 terminal output. Live-isolated frontend/Oracle verification pending; npm reported one high-severity vulnerability, investigation required before deployment.
- **M2:** Inspector → Snapshot → reviewed Catalog (no automatic WARNING→READY) and **keyword-only Catalog usability** without embedding/LLM. Confirm existing backend operation when both `LLM_BASE_URL` and `EMBEDDING_BASE_URL` are unset.
- **M3 (revised core):** **no-LLM Query Template authoring** via safe UI: schema/table/column selection from approved Catalog, constrained WHERE operators and named parameters, relation joins only via validated FK/Semantic Mapping, row cap, timeout, preview SQL and explicit DRAFT→review→approve→enable. Reuse `StructuredQueryPlan`/`query_compiler` contracts when practicable, with independent approval and execution eligibility. Optionally allow administrator SQL manual editing **subject to all existing validation**. Natural language SQL drafting is **not an acceptance criterion**.
- **M4:** keyword/lexical Template recommendation **without LLM** using existing scored candidates, explicit parameter-entry form + deterministic validation, preview → bounded Oracle Mock SELECT → durable audit. Out-of-scope/unresolved intent must ask the user to choose a template/field; never fabricate SQL or clinical identifiers.
- **M5:** MCP server discovery (keyword mode), approved template prepare/execute using the identical Web policy+audit path. Add deterministic Template discover/recommend Tool if necessary after Mode A works; existing `demis.prepare_query` accepts IDs, not raw natural language.
- **M6:** separate isolated **MCPFlow ↔ DQA** combined test once M4/M5 PASS: tool registration, caller identity, end-user authorization, trace correlation, ambiguous inputs, denial, timeout, read-only Mock results. No other product configuration/production gateway exposure without separate approval.
- **B/C later:** benchmark CPU embedding runtime and optional deployment **after software/model license and military site approval**, verify CPU memory/latency/throughput. Generative LLM activation later requires new independently approved change and strictly opt-in policy; does not change zero-model correctness/permission boundaries.

## 5. Recommended acceptance scenarios for Mode A

1. Start isolated DQA without **LLM_BASE_URL, LLM_MODEL, EMBEDDING_BASE_URL, EMBEDDING_MODEL**; backend and UI remain usable.
2. Create/select approved Oracle Mock target, Inspector metadata capture, Snapshot/catalog review and keyword schema search.
3. Graphical constrained query plan/Query Template DRAFT with verified metadata; administrator review and explicit approval/enable.
4. Input Korean keyword/phrase to find an **existing approved template**, then explicitly select and enter any patient/code/group filter parameters; no model call.
5. Execute using read-only `DEMIS_RO`, verify correct synthetic rows, row caps, timeouts, audit and safe error messages; verify 403, stale catalog, ambiguous request and missing value block execution.
6. Repeat via existing MCP Tool APIs and later via MCPFlow in a separately authorized integration environment. No real DEMIS, no clinical data, no uncontrolled writes.

## 6. Decision tradeoffs

- Some open-ended natural-language requests will not map to a template. Return **no match / choose a query / fill parameter** rather than attempting SQL generation.
- CPU semantic embedding can improve Korean paraphrase discovery but does not guarantee SQL correctness. A governed catalog and template library are still required.
- Hybrid/semantic results must have an understandable disabled/fallback state without an embedding server; no implicit GPU/model install or external data egress.
- No need to reserve GPU RAM/VRAM for DQA, but the CPU/RAM/storage/IO overhead of PostgreSQL, metadata indexing and possible CPU inference **must** be sized and approved independently from the H200 model runtime.
