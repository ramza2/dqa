# Audit retention policy (operational boundaries)

This document defines how DQA treats `query_audit_events` retention.
It does **not** hardcode a retention duration.

## 1. Append-only during normal operation

Query Audit Events are append-only while the application is running.

- Normal APIs may create audit rows as part of the query lifecycle.
- There is **no** public DELETE or PATCH API for audit events.
- `query_operator` and other application roles cannot purge audit history
  through the product API surface.

Current persisted content (NAMES_ONLY):
- identifiers (audit_id, actor/source/template/profile references)
- status / timing / count metadata
- parameter **names** (and sensitive-name flags) only

Not persisted:
- parameter values
- SQL text
- result rows
- credentials / host / DSN details

## 2. Retention duration is external governance

Retention length is **not** hardcoded in application settings because
project/site policy is not yet confirmed.

Until an approved retention policy exists:
- do not automatically delete audit records
- do not schedule unattended purge jobs from this repository
- treat audit history as durable operational evidence

## 3. Purge requirements (future, out of scope here)

Any future purge must satisfy all of the following:

1. An explicit, approved retention policy exists (duration + legal basis).
2. Purge selection is based on `created_at` (time window), not ad-hoc IDs.
3. Purge is an **offline / privileged maintenance** action — never reachable
   by `query_operator` (or other product roles) through public APIs.
4. Purge execution itself is recorded externally/operationally
   (who, when, policy reference, row count removed, window).
5. Application runtime remains append-only.

This PR does **not** implement purge tooling.

## 4. Operator inspection (read-only)

Operators may inspect aggregate retention window metadata:

```bash
./scripts/dqa-audit-retention-status.sh
```

Output is limited to:
- oldest `created_at`
- newest `created_at`
- total event count

It must not print actor IDs, source names, audit IDs, parameter names, or
result-related details.

## 5. Relationship to backups

DQA PostgreSQL backups may include `query_audit_events`.
Backup storage, encryption, and backup retention are separate site policies
from application audit purge. See `docs/runtime-and-deployment.md`.
