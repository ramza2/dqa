"""Regression tests for Alembic assets path resolution."""

from pathlib import Path

from app.adapters.db import migration_head


def test_backend_root_source_checkout():
    root = Path(__file__).resolve().parents[1]
    assert migration_head._backend_root() == root


def test_backend_root_installed_package(monkeypatch, tmp_path):
    """Installed app package must find Alembic assets in its working root."""
    installed_module = (
        tmp_path / "site-packages"
        / "app" / "adapters" / "db" / "migration_head.py"
    )

    app_root = tmp_path / "deployment"
    (app_root / "alembic" / "versions").mkdir(parents=True)
    (app_root / "alembic.ini").write_text(
        "[alembic]\nscript_location = alembic\n"
    )

    monkeypatch.setattr(migration_head, "__file__", str(installed_module))
    monkeypatch.chdir(app_root)

    assert migration_head._backend_root() == app_root

    config = migration_head._alembic_config()
    assert config.get_main_option("script_location") == str(
        app_root / "alembic"
    )
