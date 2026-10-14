# S-04-C-2B-2A — Preflight Evidence Contract + Synthetic Provider

**Status: Draft; no deployment/merge.** Companion to Draft PR #77
(`docs/schema-independent-preflight-contract-proposal.md`).
This PR requires **no** Alembic migration, environment variable,
HTTP route, Oracle connection, external service, persistent event,
Catalog import or active pointer change.

## Purpose

Introduce a small, deterministic and **non-authoritative** internal comparison
contract before military/DEMIS DBA approval of any independent evidence issuer.

Current live DQA remains at `20261014_ss02` (PR #76), with
Schema Inspector capture and human change-review journaling default-disabled.
Nothing in this implementation enables them.

## Implemented code

- `app/services/schema_preflight_contract.py`:
  `SnapshotPreflightContext` is an **internal expected** source/revision/fingerprint/
  target binding derived, in a later caller, from source-scoped immutable Snapshot
  history after the existing S-04-C-2A integrity check. It is never client-supplied.
- `ProposedEvidenceEnvelope` holds **claims** about an observed metadata
  fingerprint, its source/revision/target, issuer ID, evidence ID, collection/
  issuance/expiry and coverage. `issuer_id` is untrusted claim text, **not**
  authenticated identity or DBA authorization.
- `EvidenceProvider` is only a protocol for future approved integration.
  `UnconfiguredEvidenceProvider` is a safe no-I/O default.
  **No production provider is implemented or selectable.**
- `check_preflight_evidence_contract(...)` implements deterministic syntax,
  source/revision/target, canonical fingerprint, six metadata-category coverage,
  non-empty omission rejection and basic timezone/ordering/expiration checks.
  It fails closed for a superseded or unverified Snapshot, missing provider,
  provider failure, corrupt payload and mismatch. It returns only coarse
  reason codes, never raw schema, SQL, secrets or exception details.
- A separately constructed synthetic SchemaSnapshot is fed through
  `tests/mock_schema_preflight_provider.py`. This fake is under `tests/` only;
  it does not read Oracle, execute SQL, authenticate a DBA, or attest
  independent provenance. For the mock, equality proves **only** the
  correctness of our normalization/comparison contract.

The evaluator **always** returns:
- `preflight_status='NOT_VERIFIED'`;
- `independently_authenticated=false`;
- `replay_protected=false`;
- `revocation_checked=false`;
- `catalog_ready=false`;
- `activation_eligible=false`.

Even on a perfect mock match, only
`reason_code='STRUCTURAL_MATCH_ONLY'` and `structural_match=true` appear.
This is **not** evidence acceptance or a READY-preparation decision.

## Not yet implemented (must remain blocked)

- Real DBA/DEMIS independent evidence provider or trusted issuer/verification
  service; any approval to access live DEMIS metadata.
- Cryptographic signature verification / mTLS issuer authentication, trust
  anchors, separate issuer/operator duties, key rotation, revocation.
- Durable evidence ID/nonce anti-replay registry and audit, time validity
  policy beyond minimal ordering/expiry, environment identity attestations,
  completeness/supported-omissions policy for real Oracle dictionary views,
  authoritative external-schema FK review.
- Authenticity and freshness checks binding evidence to current reviewer
  `ACKNOWLEDGED` event and role policy.
- Production IdP, positive `VERIFIED` status, READY promotion,
  v2 Catalog Package generation/import and manual activation.
- HTTP exposure, DB schema/migration, scheduled collection, secrets,
  VLM/LLM, patient or medical-data access.

Do not take `STRUCTURAL_MATCH_ONLY` as signoff. No code may change
Catalog activation policy based on this function's result.

## Verification plan

1. Run isolated unit tests
   `backend/tests/test_schema_preflight_contract.py` (no DB).
2. Run existing `test_schema_snapshot_review.py`,
   `test_schema_snapshot_review_events.py`,
   `test_schema_snapshot_history.py`,
   `test_schema_catalog_candidate.py` and relevant Catalog validators.
3. Verify `git diff --check` and unchanged Alembic revision head.
4. No live DQA migration, Backend rebuild or deployment is necessary until a
   user explicitly approves a later PR; even then this code adds no runtime API.

## Decision dependency

The future path is: (1) accept/revise the **design** in PR #77; (2) obtain
written military/DEMIS DBA and security approval of evidence issuer and
authentication mode; (3) implement a production verifier adapter plus
independent provenance / revocation / durable replay protection in a
separate PR; (4) add isolated PostgreSQL integration; (5) independently
review policy-versioned readiness and explicit Catalog activation.
No external approval has yet been supplied.
