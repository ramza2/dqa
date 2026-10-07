"""Read-only Alembic head verification for DQA PostgreSQL.

Shared by application startup and the CLI preflight helper. Never upgrades,
downgrades, stamps, or otherwise mutates schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine


class MigrationHeadError(RuntimeError):
    """Fail-closed when the database is not at every current Alembic head.

    Message is sanitized: never includes DSN, password, host, or SQL payloads.
    """


@dataclass(frozen=True)
class MigrationHeadStatus:
    """Result of a non-destructive Alembic head inspection."""

    ok: bool
    reason_code: str
    script_heads: tuple[str, ...]
    current_heads: tuple[str, ...]
    detail: str


def _backend_root() -> Path:
    # app/adapters/db/migration_head.py -> backend/
    return Path(__file__).resolve().parents[3]


def _alembic_config(alembic_ini: Path | None = None):
    from alembic.config import Config

    ini_path = alembic_ini or (_backend_root() / "alembic.ini")
    cfg = Config(str(ini_path))
    # Absolute script_location so callers need not share a particular cwd.
    cfg.set_main_option("script_location", str(_backend_root() / "alembic"))
    return cfg


def inspect_migration_head(
    *,
    engine: Engine | None = None,
    alembic_ini: Path | None = None,
) -> MigrationHeadStatus:
    """Inspect whether the database revision set equals every script head.

    Read-only: opens a connection and queries Alembic metadata only.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine, text

    from app.core.config import get_settings

    try:
        cfg = _alembic_config(alembic_ini)
        script = ScriptDirectory.from_config(cfg)
        heads = tuple(sorted(script.get_heads()))
    except Exception as exc:  # noqa: BLE001 — sanitize import/config failures
        return MigrationHeadStatus(
            ok=False,
            reason_code="script_directory_error",
            script_heads=(),
            current_heads=(),
            detail=f"Alembic script directory error ({exc.__class__.__name__})",
        )

    if not heads:
        return MigrationHeadStatus(
            ok=False,
            reason_code="no_script_heads",
            script_heads=(),
            current_heads=(),
            detail="no Alembic heads in script directory",
        )

    # settings/URL/engine creation + connect/inspection share one fail-closed
    # boundary so raw exceptions (including credential-bearing messages) never
    # escape. Injected engines are not disposed by this helper.
    owns_engine = False
    bind: Engine | None = None
    current: tuple[str, ...] = ()
    try:
        if engine is None:
            # Throwaway engine; never log URL (may embed credentials).
            bind = create_engine(get_settings().database_url)
            owns_engine = True
        else:
            bind = engine

        with bind.connect() as conn:
            has_version_table = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version'"
                )
            ).scalar()
            if not has_version_table:
                return MigrationHeadStatus(
                    ok=False,
                    reason_code="alembic_version_absent",
                    script_heads=heads,
                    current_heads=(),
                    detail="alembic_version table is absent",
                )

            context = MigrationContext.configure(conn)
            current = tuple(sorted(context.get_current_heads()))
    except Exception as exc:  # noqa: BLE001 — never echo connection details
        return MigrationHeadStatus(
            ok=False,
            reason_code="database_error",
            script_heads=heads,
            current_heads=(),
            detail=f"database/Alembic error ({exc.__class__.__name__})",
        )
    finally:
        if owns_engine and bind is not None:
            bind.dispose()

    if not current:
        return MigrationHeadStatus(
            ok=False,
            reason_code="no_current_revision",
            script_heads=heads,
            current_heads=(),
            detail="no current Alembic revision recorded",
        )

    head_set = set(heads)
    current_set = set(current)
    if current_set != head_set:
        missing = sorted(head_set - current_set)
        extra = sorted(current_set - head_set)
        detail_parts: list[str] = []
        if missing:
            detail_parts.append(f"missing heads={','.join(missing)}")
        if extra:
            detail_parts.append(f"unexpected revisions={','.join(extra)}")
        detail = "; ".join(detail_parts) if detail_parts else "revision set mismatch"
        return MigrationHeadStatus(
            ok=False,
            reason_code="not_at_head",
            script_heads=heads,
            current_heads=current,
            detail=detail,
        )

    return MigrationHeadStatus(
        ok=True,
        reason_code="at_head",
        script_heads=heads,
        current_heads=current,
        detail="database is at Alembic head",
    )


def assert_migrations_at_head(
    *,
    engine: Engine | None = None,
    alembic_ini: Path | None = None,
) -> MigrationHeadStatus:
    """Raise MigrationHeadError unless the database is at every script head."""
    status = inspect_migration_head(engine=engine, alembic_ini=alembic_ini)
    if status.ok:
        return status
    raise MigrationHeadError(status_message(status))


def status_message(status: MigrationHeadStatus) -> str:
    """Operator-facing one-line status (sanitized)."""
    if status.ok:
        return "migration check ok: database is at Alembic head"
    if status.reason_code == "not_at_head":
        return f"migration check failed: database is not at Alembic head ({status.detail})"
    return f"migration check failed: {status.detail}"
