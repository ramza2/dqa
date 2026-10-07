"""Fail closed unless the DQA database Alembic revision set equals script heads.

Used by on-prem ``dqa-up.sh`` as a non-destructive preflight. Does not upgrade,
downgrade, or mutate schema. Exit codes:

* 0 — database is at every current Alembic head
* 1 — not at head / no alembic_version / connectivity or Alembic error

Never prints database passwords or DSNs.

Logic lives in ``app.adapters.db.migration_head`` so application startup and
this CLI share one checker.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from app.adapters.db.migration_head import inspect_migration_head, status_message
    except Exception as exc:  # noqa: BLE001 — fail closed with safe message
        print(
            f"migration check failed: import error ({exc.__class__.__name__})",
            file=sys.stderr,
        )
        return 1

    status = inspect_migration_head()
    message = status_message(status)
    if status.ok:
        print(message)
        return 0
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
