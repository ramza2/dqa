# M5-UX3D — Snapshot History shared Source defaults

## Operator behavior

- The active Catalog Source picker in the Data Discovery toolbar remains enabled
  on **스키마 변경 이력**, as on the other Discovery tabs.
- Once the permission-filtered active Catalog selection has loaded, Snapshot
  History automatically issues a **read-only** Source-scoped GET for that Source.
  Changing the toolbar Source reloads the history and invalidates pending list,
  Diff, Review Preview and review-event responses from the previous Source.
- The ordinary Snapshot view no longer has a duplicate Source textbox or
  **Snapshot 조회** button. The current Source is displayed with a short hint.
- **다른 소스의 스냅샷 조회** reveals the legacy exact-Source input only as an
  explicit exception. This does not alter the active Catalog selection. Closing
  the exception returns to the selected Catalog Source automatically.
- If no active Catalog is available (including insufficient Catalog list
  permission), the independent Snapshot-only Source input remains available.
  Snapshot authorization is still enforced by the existing backend endpoint.
- An empty Snapshot list is valid even when the active Catalog is READY.
  Snapshot revision IDs, Catalog import revision IDs and matching fingerprints
  remain independent; none imply DBA approval or activation.

## Original Analyzer / previous DQA behavior comparison

| Previous DQA / parity baseline | M5-UX3D | Safety / intentional divergence |
| --- | --- | --- |
| Manually enter exact Snapshot Source and click Search | Auto-read shared selected active Catalog Source | This is a navigation default, not Snapshot/DB access authority |
| Snapshot-only Source can be queried without active Catalog | Preserved as exceptional manual path | Backend permission and Source validation unchanged |
| Catalog toolbar disabled on Snapshot tab | Same usable selector as other Discovery tabs | Selected Source still revalidated against active Catalog list |
| Snapshot detail Diff, review status and journal GETs | Unchanged | Existing Source/Revision/Fingerprint and stale-response guards retained |

## Verification

- `SchemaSnapshotHistory.test.tsx`: automatic Source on tab entry, no default
  search form, stale active-Source list guard, manual non-active Source return,
  no-active Catalog fallback and existing review/Diff security tests.
- `CatalogSourceSharing.test.tsx`: toolbar selection remains enabled on Snapshot
  and drives two successive source-scoped GETs.
- Frontend build, lint and targeted Vitest tests are the code-level gate;
  LAN Oracle Mock runtime validation remains separate.

No API, database schema, Oracle data/privilege or Catalog activation changes.
