# M2-0 — DQA operator workflow landing page (2026-10-27)

## Decision

The normal first screen is **Dashboard**, not Query Assistant. Existing profiles,
Data Discovery and read-only Query Assistant remain accessible. The dashboard
describes the intended sequence:

1. Register an explicit Target/Profile.
2. Inspect schema metadata with a separately permitted Inspector identity.
3. Review and activate an eligible Catalog revision; search the active Catalog.
4. Confirm the in-scope clinical-information groups and table/field mapping with DEMIS functional owners; 11 groups is not a finalized scope.
5. Review and approve constrained Query Templates.
6. Expose approved template operations using authorized MCP/internal REST clients.

M2-0 is **only the navigation/workflow shell**. "화면 이용 가능" means the
existing page can be opened, not that live DEMIS or its security gates passed.
Unimplemented steps have no action buttons, and the current assistant is
explicitly a **test surface**, not the first administrative workflow.

## Next scoped changes — NOT implemented by M2-0

- **M2-1:** remove the Mock quick-prepare dependency; register Mock using the
  same explicit Target wizard used for authorized real read sources, but keep
  an isolated development-only allowlist and mock credential policy. Connect
  Profile -> Inspector Target **only after** eligibility/preflight checks.
- **M2-2:** approved metadata-only Inspector -> Snapshot -> validated v2
  package -> review/READY-only explicit Catalog activation. Keep old revision
  on every error; no WARNING automatic promotion.
- **M2-3:** lexical retrieval first; CPU embedding optional and site-approved.
  Clinical-information scope and table mappings need DEMIS owner review (not an assumed 11 groups or embedding guesses).
- **M3-M5:** structured Oracle SELECT preview, independently approved query
  template with explicit parameters, bounded read/MCP execution and audit.
- Future generative model: optional, separately approved, SQL draft only;
  no arbitrary SQL execution.

## Site facts / gates

Oct 26 DBA discussion: Oracle 19c, >=8,000 tables, 12 hospital source DBs,
GoldenGate data propagation is table-dependent; no dedicated ODS. Daejeon DR
is **not** approved for queries. Actual query source, target metadata grants,
tables/ERD and network access remain pending. Do not hard-code Oracle Mock
schema or assume source equivalence.

DQA is an internal implementation/verification tool, **not a separately
approved military application**. Official deliverables remain DEMIS integration.
Do not deploy or connect to real DEMIS from this PR; maintain read-only and
secret/authorization boundaries.
