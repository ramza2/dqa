# S-04-C-2B-2 — independent Schema metadata preflight: proposed contract (decision pending)

> **Proposal only, not an approved military/DEMIS policy.** This document
> defines design decisions and testable safety boundaries before any code/API
> or database migration. Do not interpret it as DBA acceptance or permission
> to connect to live DEMIS. No runtime changes in this PR.

## Baseline (verified development implementation)

- S-04-C-1: admin-only Snapshot capture, append-only `schema_snapshot_revisions`.
- S-04-C-2A: `GET .../snapshots/{revision_id}/review` verifies stored
  Snapshot integrity, Diff and offline v2 `WARNING` candidate only.
  `preflight_status=NOT_VERIFIED` and `activation_eligible=false`.
- S-04-C-2B-1: append-only admin **change-review** journal
  `schema_snapshot_review_events`; `ACKNOWLEDGED`/ `CHANGES_REQUESTED`
  is not independent DBA verification or Catalog approval.
  `DQA_SCHEMA_SNAPSHOT_REVIEW_ENABLED` is default-off, dev/test only.
- Development deployment after PR #76: Alembic `20261014_ss02`, active
  `oracle_demis_mock` Catalog Revision #1 READY. Both Inspector collection
  and admin review recording remain **disabled**. There are zero captured
  Snapshot revisions or review events in this baseline.
- Existing Catalog import and READY-only manual activation are independent
  authorities. Real DEMIS clinical data and write operations remain out of scope.

## Proposed independent evidence trust boundary

A second invocation of the same DQA inspector / self-comparison of its
Snapshot / a second DQA admin checkbox **does not** establish independence.

**Preferred architecture for external decision:** an independently authorized
military/DEMIS DBA metadata inspection process (separate operating principal,
approved read-only dictionary scopes and independently controlled execution)
issues bounded, authenticated evidence. DQA validates proof using a configured
**trusted issuer/verifier** and compares independently observed normalized
metadata to an immutable DQA Snapshot. DBA inspection does not read medical
rows, execute arbitrary SQL, or edit DEMIS.

Alternative trust models to be approved *before implementation*:

1. **Signed DBA-attested evidence** with approved key management,
   authorized issuer identities and revocation/recovery process.
2. **Authenticated DBA preflight verification API** with secure service-to-service
   authentication, independent inspection provenance and revocation checks.
3. **Separately managed trusted metadata agent** with distinct DBA-approved
   credentials, deployed/controlled outside the DQA application trust boundary
   and issuing verifiable evidence. Merely switching env var credentials within
   the same untrusted operator context is insufficient.

Do not treat a manually uploaded unsigned JSON, client-specified
`preflight_passed=true`, existing `dev_headers` identity, or a generated
metadata fingerprint **alone** as proof of independence.

## Candidate evidence envelope (illustrative field-level contract)

The fields below are **proposed**, not an approved schema or API.

| Group | Proposed required fields | Verification / rule |
|---|---|---|
| Evidence identity | `evidence_id` (unique), schema version, issuance nonce | Reject replay or ID reuse with differing content |
| Issuer | issuer ID, independently authenticated authority, method, signature/proof reference | Verify trusted issuer allowlist, key/identity status and approved scope; never trust payload assertion alone |
| Target | `source_name`, DB type, database and schema identity, environment identifier | Must match configured source and Snapshot exact physical target |
| Snapshot binding | immutable `snapshot_revision_id`, canonical `schema_fingerprint`, capture time | Compare against immutable stored Snapshot; latest-only gate for new acceptance |
| Independent observation | canonical physical metadata digest, collection method/version, covered dictionary categories | Exact normalization parity; independently collected digest is not just a copy of Snapshot digest |
| Scope/completeness | approved allowlist, object counts by type, enumerated omissions/unsupported objects | DBA-defined policy; unknown omissions or insufficient metadata privilege -> reject |
| Time | `observed_at`, `issued_at`, `not_after` | Trusted clock / duration policy; expired or implausible future evidence -> reject |
| Review binding | reviewer event reference and current decision/fingerprint | `ACKNOWLEDGED` is necessary only if explicitly agreed; never sufficient by itself |
| Revocation | revocation identifier/status check, trust-anchor version | Missing/unknown revocation status is not positive evidence |
| Audit | verifier identity, verification time, deterministic result/reason code | Append only; never persist credentials, patient data or unrestricted raw evidence |

### Fingerprint and completeness warning

Current `schema_catalog_candidate._physical_payload` intentionally normalizes
metadata and omits potentially sensitive Oracle defaults and index definitions.
Matching its SHA-256 digest **does not prove permission completeness or coverage
of excluded/unsupported metadata**. For an independent verification, the DBA
must sign off coverage and omissions (external-schema FKs, dictionary-view
visibility, views/synonyms, expression indexes, unsupported objects) and
specify exactly which fields must match. An evidence issuer must independently
observe the data; DQA must not synthesize its proof from a stored Snapshot.
Do not quietly loosen mismatch handling to gain a `VERIFIED` result.

## Proposed fail-closed evaluation contract

**No implementation is authorized by this draft.**

1. Authenticate requester through approved principal/permission (no production
   `dev_headers`). Require explicit source/revision and expected fingerprint.
2. Verify issuer signature or authenticated independent service origin.
   Trust configuration/revocation/issuer authority must be server-controlled,
   never taken solely from submitted JSON.
3. Check evidence ID replay, expiry, target/environment/scope/privilege coverage,
   independent observation time and full normalized metadata comparison.
4. Under a source-scoped transaction lock, re-read immutable Snapshot,
   latest revision, Review journal and currently valid evidence. Recheck
   after slow external calls; never hold DB lock across an Oracle/network call.
5. Record a deterministic append-only verification event if authorized;
   show signed metadata summary only and no secrets/raw patient data.
6. Treat uncertainty, unverifiable issuer, mismatch, expired/revoked proof,
   newer Snapshot and changed review decision as **NOT_VERIFIED/BLOCKED**.
7. The evaluation event cannot directly create/import a READY package,
   grant Catalog activation or change Query Template eligibility.

Suggested display states: `NOT_VERIFIED`, `VERIFICATION_FAILED`,
`VERIFIED`, `EXPIRED`, `REVOKED`, `SUPERSEDED`.
Their final semantics and persistence model are **TBD by approved policy**,
not defined by the current software.

## Separation from READY promotion and Catalog activation

Even positive independent evidence remains a **single gate**. A separate
reviewed PR must define signoff roles, policy version, evidence/Review
cross-checks, handling of `CHANGES_REQUESTED`, explicit `READY` candidate
generation using existing v2 package validator, immutable Catalog import,
and **explicit** manual READY-only activation. Source change, fingerprint
change, expired/revoked evidence or altered review policy invalidates prior
eligibility. On any failure retain existing active Catalog Revision #1 (or
the then-current authoritative revision). No automatic rollback pointer swap.

## Acceptance tests for a later implementation

Synthetic fixtures only, disposable PostgreSQL, no live DEMIS:
- valid independently sourced and authenticated evidence only after all
  approved policy gates; no positive acceptance without trusted issuer proof;
- altered signature, forged issuer, unsigned upload, expired/revoked/unknown,
  replayed nonce, tampered digest, wrong source/DB/schema/environment,
  mismatched fingerprint, stale Revision and review sequence rejected;
- incomplete privileges, invisible FK/constraint/index or documented omitted
  metadata policy rejected when coverage unsatisfied;
- concurrent evidence submissions, CAS conflict, network failure between
  verify and commit, rollback and duplicate request semantics;
- neither accepted nor rejected evidence changes Catalog active pointer,
  Query Template eligibility or DEMIS data; no secrets in log/API/audit;
- default-disabled and production blocked until approved IdP/issuer/DBA policy,
  with explicit staging and rollback verification.

## Open decisions — obtain written agreement before coding a VERIFIED path

| Decision | Accountable partner | Default before agreement |
|---|---|---|
| Which independent evidence trust model: signed DBA bundle, authenticated DBA verification API or external controlled agent? | 군/DEMIS 운영·DBA, 보안 | No trusted issuer; `NOT_VERIFIED` |
| Who signs / controls keys, verification credentials, rotation, revocation and separation of duties? | 군/DEMIS 운영·보안 | No acceptance |
| Allowed target schemas, Oracle ALL_* privilege scope, completeness and acceptable omissions (including cross-schema relations)? | DBA·SA | Block any unsupported claims |
| Exact canonicalization, capture/independent observation TTL, clock skew and drift tolerances? | DBA·SA·보안 | No verified status |
| Which reviewer role / decision is required, and what re-review/supersession policy? | PM/PL·군·보안 | No READY promotion |
| How to version/retain evidence with privacy controls and recover trust anchors? | 보안·DBA·QA | No persistence of raw evidence |
| Authorization to test with real military DEMIS metadata and institution acceptance? | 군/병원 | Synthetic mock only |

**Recommended next action:** get a decision on independent evidence origin
and issuance/verification authority, then implement a small fail-closed
`verification contract + fake provider + synthetic tests` PR first.
Actual independent connector and READY-promotion logic belong in later,
separately reviewed PRs.
