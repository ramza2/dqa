# M5-UX1: Table Explorer parity slice (2026-11-04)

## Scope and reference

Reference: `ramza2/demis-schema-search-poc/frontend/table_explorer.py` and
`frontend/pages/2_Table_Explorer.py`. This slice improves DQA's existing
**active Catalog read-only** explorer. It does not read from the PoC database,
call Oracle, create a Snapshot, or change Package activation.

| PoC Table Explorer behavior | DQA M5-UX1 | Intentional difference / follow-up |
| --- | --- | --- |
| Target selector and analysis-run fingerprint | Active Catalog source, immutable revision and fingerprint header | Only activated READY Catalog is authoritative; no unaudited analysis-run fallback |
| Schema and Category filters, table/comment search | Server-side `schema_name`, `category`, `q` bounded queries | Schema accepts an exact name, including names outside the first returned page; no implicit scan of all table pages |
| Tables list and comments | Selectable, bounded list; returned/total counts and truncation notice | API is limited to 500 per response; tighten filters when result is truncated |
| Table overview and summary metrics | Overview and visible Column / outgoing FK / incoming FK / Index counts | These are *loaded* metadata counts, not independent source/database estimates |
| Columns, Relations, Indexes, Categories tabs | Four native React detail tabs, with directional FK groups | Category assignment details are bounded by the category response; table category keys remain visible if a category name is unavailable |
| Technical information disclosure | Collapsible table type / category key details | PoC-specific object ID, live-analysis run and fingerprint fields are not available from active Catalog table detail API |
| ERD button | Existing focused, 1-hop relationship overview retained | Full React Flow + ELK, category/full ERD, minimap/zoom are **not** delivered by this slice |

## Invariants

- All table, column, relation, index and category reads use the existing
  `catalog/active/{source}` permission-gated metadata API. No write actions.
- Filters are evaluated by the server **before pagination**; a locally
  truncated 500-table page must never be mistaken for the complete schema.
- Returned source/revision/fingerprint metadata must match the active Catalog
  pointer. Previous-revision lists/details are hidden before replacement.
- Source change resets table search, schema and category filters and selection.
- Category assignments require exact schema + table matches; missing category
  display metadata does not erase an authoritative category ID on a table.

## Verification

- Frontend `npm run build`, `npm run lint`, and `npm run test -- --run`.
- Synthetic Oracle Mock tests cover server-side filter parameters, table
  detail/relationship/index tabs, category assignment display, bounded-page
  warning, source switch and stale revision rejection.
- Real DEMIS connection, clinician data, production DB mutation, authentication
  changes and site/DBA approvals are outside this slice.

## Next parity slices

1. Full/Category/Focused ERD using reviewed PoC React Flow + ELK rendering,
   bounded layout and approved active-Catalog relation APIs.
2. Left navigation/workspace parity and DB Analysis Preflight entry point,
   respecting distinct Snapshot vs Catalog authority.
3. Report, Schema Run Diff and Catalog Package workspace parity on existing
   authorized DQA read-only/review endpoints.
