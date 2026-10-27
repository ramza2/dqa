# M2-1C: Oracle Mock Inspector privilege visibility diagnostic

Status: **read-only test helper**, no runtime DQA deployment/Oracle DCL.
M2-1B main commit is `2a4503a`. Operator verified Oracle Mock has 25
DEMIS_OWNER tables, 206 columns, 25 DEMIS_RO SELECT grants. Independent
DEMIS_INSPECT_RO was created with CREATE SESSION only.

## Run (after main merges this PR)

```bash
cd ~/dqa
bash scripts/dqa-m2-1c-inspector-privilege-check.sh
echo "PUTTY_SESSION_ALIVE"
```

Run as an external `bash` child process, **not `source`**; nonzero exit
cannot close the caller's SSH session. Never enable shell xtrace around the
secret. Only the owner-readable (0600) file
`~/.config/dqa/m2-1b-mock-inspector.env` is consulted.

The script pins the Oracle Free Mock image, health and FREEPDB1 identities;
verifies source schema footprint and Inspector privilege baseline; checks
Oracle `ALL_*` dictionary visibility as DEMIS_INSPECT_RO; proves business
row SELECT denied using `WHERE 1=0` (no rows fetched). It performs no SQL
CREATE, GRANT, REVOKE, Catalog import/activation or Snapshot capture.

With CREATE SESSION only, `M2_1C_METADATA_INCOMPLETE` is expected.
`M2_1C_READ_ONLY_DIAGNOSTIC_COMPLETED` means diagnostics completed,
**not** that the Inspector is authorized or metadata is complete.
Only `M2_1C_METADATA_READY` means 25 visible tables/206 columns plus
nonzero FK and index counts and confirmed row SELECT denial.

## Separate future decision

Oracle `ALL_*` depends on current user's object accessibility.
Do **not** give SELECT ANY TABLE/SELECT ANY DICTIONARY or wholesale business
table SELECT just to populate catalog views. REFERENCES may expose metadata
but is a DDL-related FK privilege, not innocuous read access. If pursued,
test a single object on a **disposable Oracle fixture** and revoke after
verification, independently of this script.

Alternative: approved metadata-only DBA export with offline signed snapshot
validation. No military DBA authorization, real DEMIS connection, or
operational DQA DB change is implied. Use disposable PostgreSQL before any
new Snapshot acceptance.
