"""Fail closed unless the DQA database Alembic revision set equals script heads.

Used by on-prem ``dqa-up.sh`` as a non-destructive preflight. Does not upgrade,
downgrade, or mutate schema. Exit codes:

* 0 — database is at every current Alembic head
* 1 — not at head / no alembic_version / connectivity or Alembic error

Never prints database passwords or DSNs.
"""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from sqlalchemy import create_engine, text

        from app.core.config import get_settings
    except Exception as exc:  # noqa: BLE001 — fail closed with safe message
        print(f"migration check failed: import error ({exc.__class__.__name__})", file=sys.stderr)
        return 1

    try:
        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        heads = set(script.get_heads())
        if not heads:
            print("migration check failed: no Alembic heads in script directory", file=sys.stderr)
            return 1

        # Use a throwaway engine; do not log URL (may embed credentials).
        engine = create_engine(get_settings().database_url)
        with engine.connect() as conn:
            # Fresh DB: alembic_version may be absent.
            has_version_table = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                )
            ).scalar()
            if not has_version_table:
                print("migration check failed: alembic_version table is absent", file=sys.stderr)
                return 1

            context = MigrationContext.configure(conn)
            current = set(context.get_current_heads())
    except Exception as exc:  # noqa: BLE001 — sanitize; never echo connection details
        print(
            f"migration check failed: database/Alembic error ({exc.__class__.__name__})",
            file=sys.stderr,
        )
        return 1

    if not current:
        print("migration check failed: no current Alembic revision recorded", file=sys.stderr)
        return 1

    if current != heads:
        # Support multiple heads: every head must be present in the DB revision set.
        missing = sorted(heads - current)
        extra = sorted(current - heads)
        detail_parts: list[str] = []
        if missing:
            detail_parts.append(f"missing heads={','.join(missing)}")
        if extra:
            detail_parts.append(f"unexpected revisions={','.join(extra)}")
        detail = "; ".join(detail_parts) if detail_parts else "revision set mismatch"
        print(f"migration check failed: database is not at Alembic head ({detail})", file=sys.stderr)
        return 1

    print("migration check ok: database is at Alembic head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
