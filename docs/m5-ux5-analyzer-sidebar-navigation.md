# M5-UX5 — Analyzer-style sidebar and direct Catalog navigation (2026-11-05)

## Reference and scope

Compared the legacy `ramza2/demis-schema-search-poc` multipage shell
(`frontend/app.py` and `frontend/pages/1_DB_Analysis_Preflight.py` through
`6_Catalog_Package.py`) with the DQA native `App`, `DataDiscoveryPortal` and
`ConnectionProfilePortal`.

This UI-only slice replaces DQA's main horizontal navigation with a persistent
left workspace sidebar on desktop and a horizontally scrollable grouped menu
on narrow screens. The existing DQA components and APIs remain authoritative;
there is no PoC runtime, database, credential or Oracle dependency.

| Legacy Analyzer behavior | DQA M5-UX5 | Deliberate difference / follow-up |
| --- | --- | --- |
| Multipage navigation on the left | Grouped sidebar: Start, DB analysis, Catalog, Query/Management | Existing DQA settings, Query Assistant and Template Review remain available |
| Separate Table Explorer, ERD pages | Direct sidebar shortcuts open active-Catalog Table and ERD views | Same shared active Catalog Source/Revision/Fingerprint; no PoC Target selection |
| Schema Search and run history access | Direct shortcuts for Search, Index and Snapshot History | Snapshot is explicitly non-authoritative, with the M5-UX3D manual exception preserved |
| DB Targets / DB Analysis Preflight | Existing DB Target/Connection Profile page and precise notice about where development Inspector controls reside | No invented production Preflight route or permission to run Oracle analysis |
| DB Analysis Report, Run Diff and Catalog Package pages | Listed under *Analyzer migration pending*, without clickable execution controls | DQA has partial Snapshot review/Diff and Catalog controls, but full old-page parity is **not** claimed |

## Behavior and safety

- Clicking a Catalog sidebar item switches to the requested native DQA tab.
  The in-page subtab row is hidden **only** when the sidebar controls the tab;
  standalone `DataDiscoveryPortal` preserves the existing tab navigation.
- The Table Explorer's "view ERD" focus handoff still switches to the ERD
  view through the same parent callback; it does not load a second Catalog.
- The existing primary menu names and `tab` roles remain stable for older
  navigation automation. The active Catalog subpage exposes `aria-current`.
- The Dashboard remains the initial route, and re-opening the primary Catalog
  item goes to Schema Search. Navigating to a different primary DQA feature
  does not mutate the database or an approval state.
- Small screens show a compact scrollable navigation row; no sidebar overlay
  blocks forms, and the workspace remains width-bounded.
- Do not infer real DEMIS access, site/DBA authorization, READY activation or
  read/write permissions from navigation visibility or Oracle Mock results.

## Verification

- `npm run build` — PASS (existing large ERD chunk warning).
- `npm run lint` — PASS, with two pre-existing exhaustive-deps warnings in
  `TemplateReviewPortal.tsx` (0 lint errors).
- Targeted application/navigation tests — 70 passed.
- Full frontend Vitest regression — **280 passed across 37 files**.
- Synthetic/mock-only frontend data. No backend migration, writes, external
  service calls or on-prem runtime deployment is part of this change.
- Reviewed the original Streamlit page structure and DQA React component
  arrangement. A live side-by-side **visual** review on the on-prem development
  screen is required after the PR is merged and the frontend is deployed;
  static code and jsdom tests do not establish pixel-level parity.

## Next independent slices

1. An explicit DB Analysis Preflight workspace using **only** DQA's existing
   permission-gated Target/Inspector metadata states; no unapproved run action.
2. Separate Report, Schema Run Diff and Catalog Package page parity using
   approved, bounded, read-only or review endpoints already in DQA.
3. Final desktop/mobile visual comparison and operator usability review
   against the legacy Analyzer, with synthetic Oracle Mock data.
