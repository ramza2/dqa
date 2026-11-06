# M5-UX6 — independent DB Analysis Preflight navigation (2026-11-05)

## Scope and original Analyzer comparison

Reference: `demis-schema-search-poc/frontend/pages/1_DB_Analysis_Preflight.py`.
The original Streamlit page selected a Target, tested connectivity, discovered
schemas, chose analysis schemas and POSTed a metadata Preflight with a
READY/WARNING/BLOCKED summary. This is **not** a safe or authorized API contract
for DQA's current production-bound operating model.

| Legacy Analyzer | M5-UX6 DQA workspace | Deliberate divergence |
| --- | --- | --- |
| Separate DB Analysis Preflight page | Dedicated left-sidebar "DB 분석 사전점검" screen | Preserves other DQA navigation |
| Target selector and connection metadata | Paginated existing Connection Profiles; explicit selection; Source/Environment/DBMS/Service | No password input or secret reference rendering |
| Connection probe and schema list | Existing GET-only Profile diagnostics and explicit Inspector Target *structural comparison* | No Oracle connection, independent DBA permission/issuer claim or arbitrary schema list |
| Preflight run and summary | Pinned synthetic Mock-only GET readiness check showing server-assigned schema and reason | `READY_FOR_DEV_INSPECTION` means only *dev Inspector prerequisites*; no production READY/WARNING/BLOCKED verdict |
| Direct analysis / Snapshot actions | Not available in Preflight workspace | Existing Mock Inspector analysis/capture still has its own separate server-gated controls in Profile detail |
| Credentials/permissions | No credential value/input, no policy overrides or hidden backend state mutation | DBA/site/security authorization remains pending |

## Safety and interaction details

1. Mounting the page requests only a bounded, paginated Profile list (20/page)
   and never auto-selects a Target or probes a database.
2. Selecting a Target fetches the existing administrator-authorized Profile and
   diagnostics via GET, checks matching ID/Source/Environment/enabled flags and
   `live_connection_tested=false`, and displays masked credential *presence*.
3. The Inspector structural comparison is a separate deliberate GET. The
   existing client checks `connection_authorized=false`,
   `live_connection_tested=false`, `inspector_bound_to_profile=false` and
   `credential_values_resolved=false`. It is never called on page mount.
4. A synthetic, development-only `oracle_demis_mock` Profile may request its
   pinned readiness through another deliberate GET. The reused Inspector UI is
   in `readinessOnly` mode: **no metadata scan POST, Snapshot capture POST or
   Catalog activation control**. The schema name comes only from the server.
5. All other Target combinations show a blocked production-analysis notice,
   not a disabled but misleading generic "run preflight" button.
6. Target/page/reload changes invalidate displayed diagnostics and pending
   requests; an old response cannot overwrite a newly selected Target.
7. The backend API, authorizations, Docker images, schema, and CLI remain
   unchanged. No live DEMIS tests or on-prem deployment are part of this PR.

## Verification and follow-up

Frontend tests cover navigation, explicit GET-only actions, Mock versus
non-Mock gate, secret redaction, stale response isolation, pagination and
permission failures. Compare the new page visually with the original Analyzer
after a separate frontend-only development deployment.

- Focused navigation/Preflight/Mock tests: 10 passed.
- Frontend build: PASS; existing ERD bundle size warning remains.
- Frontend lint: 0 errors; 2 pre-existing `TemplateReviewPortal` warnings.
- Full frontend regression: **284 passed / 38 files** with
  `npm run test -- --run --maxWorkers=2`. The first unconstrained run while
  building concurrently hit four timeouts in unchanged tests; all passed on
  the bounded, separate rerun.

Outstanding work requiring independently approved design: trusted DBA Preflight
issuer/evidence, permitted schema-discovery/metadata privileges, production
connectivity, READY eligibility, and separately audited production workflows.
This UI slice does not expand those authorities.
