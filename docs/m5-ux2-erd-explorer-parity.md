# M5-UX2: active Catalog ERD Explorer parity (2026-11-04)

## Reference and boundary

Reviewed `ramza2/demis-schema-search-poc/frontend/erd_explorer.py`,
`frontend/erd_component/src/App.tsx` and its CSS. This DQA-native React
component retains the old **React Flow + ELK layered/orthogonal** experience,
without the Streamlit bridge, old PoC API/database or credentials.

Only **approved, activated, immutable Catalog Package v2** metadata from
existing permission-gated `GET /catalog/active/...` APIs is used. This is not
Inspector Snapshot/Preflight, DEMIS clinical read, DBA approval, or a write path.

## Old vs new feature checklist

| Legacy Analyzer ERD | DQA M5-UX2 | Notes |
| --- | --- | --- |
| Full / selected Table neighborhood / Category mode | All three modes | No live Target/analysis-run database; active Catalog revision is authoritative |
| 1- and 2-hop neighborhood | Both depths | Search may further reduce neighborhood results |
| React Flow table nodes and FK relations | Native React Flow and ELK layered orthogonal edges | Only FK links with both endpoints in loaded Catalog metadata are drawn |
| Table/category labels and table comments | Schema, table, comment and known category names | Unknown category name falls back to authoritative category ID |
| Pan, zoom, minimap, fit view | Available | Table editing/edge creation disabled |
| FK constraint and source/target column mapping | Clickable relation and detail area | Dense graphs hide inline edge labels; detail list provides mappings |
| Original sidebar multipage navigation | ERD tab in existing DQA Data Discovery workspace | Whole-app sidebar migration remains separate, preserving existing DQA functions |

## Large Catalog / consistency policy

- Initial data reads are paged and capped: 1,000 Tables, 2,000 Relations,
  500 Categories. Each response must match the exact source/revision/fingerprint
  and requested page; active pointer is rechecked after the batch.
- An ELK layout contains at most 80 tables and 160 relations per view.
  UI explicitly displays both source read truncation and layout omissions.
- Unknown/absent FK endpoints are counted and not fabricated as graph nodes.
- Switching Source invalidates previous asynchronous responses and selections.
- ERD code is lazy-loaded to avoid imposing React Flow/ELK bundle cost on the
  ordinary Dashboard/Search/Query Assistant landing paths.
- Layout is recomputed only when graph scope changes, not on FK selection.

## Verification

- Graph unit cases cover duplicate table names in distinct schemas, category
  filtering, 1-/2-hop neighborhoods, missing endpoints and dense graph caps.
- API loader tests cover permitted GET-only routes, pagination, partial result
  labels, fingerprint mismatch and active pointer change rejection.
- UI tests cover source switch races and view/filter/selection interactions.
- Frontend build, lint, entire Vitest suite. Synthetic data only; no real
  DEMIS, production Oracle or PHI is used.

## Open items

1. The 1,000/2,000/500 upper bounds do not constitute full coverage for a
   larger production Catalog; a future backend graph-query endpoint with
   server-side category/neighborhood filtering is preferable there.
2. PoC's Preflight, report, Run Diff, Package Finalization and left sidebar
   still require separate parity slices, with DQA review/activation gates.
