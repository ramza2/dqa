"""R-01-D: offline guard against wiring untrusted R-01-B/C drafts into runtime.

This is a static architecture regression, NOT a trust/cryptographic verification
or an enforced network allowlist. No DB fixtures, DNS, sockets or real sites.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

APP_ROOT = Path(__file__).resolve().parents[1] / "app"
DRAFT_MODULES = frozenset({
    "app.services.replica_target_screening",
    "app.services.site_target_evidence_review",
})
DRAFT_NAMES = frozenset({"replica_target_screening", "site_target_evidence_review"})
# Only the two offline draft modules may use each other.
EXCLUDED_FROM_SCAN = {
    APP_ROOT / "services" / "replica_target_screening.py",
    APP_ROOT / "services" / "site_target_evidence_review.py",
}


def _is_draft_module(name: str) -> bool:
    return any(name == draft or name.startswith(draft + ".") for draft in DRAFT_MODULES)


def _draft_reference_lines(source: str, *, in_services: bool) -> list[int]:
    """Flag direct/static imports of draft-only modules; do not execute code.

    AST cannot prove the absence of arbitrary dynamic imports or runtime
    authorization, so this guard supplements rather than replaces review.
    """
    tree = ast.parse(source)
    lines: list[int] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(_is_draft_module(alias.name) for alias in node.names):
                lines.append(node.lineno)

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if _is_draft_module(module):
                lines.append(node.lineno)
            elif module == "app.services" and any(
                alias.name in DRAFT_NAMES for alias in node.names
            ):
                lines.append(node.lineno)
            elif node.level and in_services and (
                module in DRAFT_NAMES
                or (module == "" and any(alias.name in DRAFT_NAMES for alias in node.names))
            ):
                lines.append(node.lineno)

        elif isinstance(node, ast.Call):
            # Static literal importlib.import_module / __import__ calls only.
            func = node.func
            dynamic_import = (
                isinstance(func, ast.Name) and func.id == "__import__"
            ) or (
                isinstance(func, ast.Attribute)
                and func.attr == "import_module"
            )
            if (
                dynamic_import
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and _is_draft_module(node.args[0].value)
            ):
                lines.append(node.lineno)

    return sorted(set(lines))


def test_no_runtime_module_imports_offline_policy_drafts() -> None:
    """Ensure drafts are not imported into currently deployed Python app paths."""
    errors: list[str] = []
    assert APP_ROOT.is_dir()
    for path in sorted(APP_ROOT.rglob("*.py")):
        if path in EXCLUDED_FROM_SCAN:
            continue
        lines = _draft_reference_lines(
            path.read_text(encoding="utf-8"),
            in_services=path.parent == APP_ROOT / "services",
        )
        if lines:
            errors.append(f"{path.relative_to(APP_ROOT)}:{','.join(map(str, lines))}")
    assert not errors, "Unreviewed draft-policy wiring detected: " + "; ".join(errors)


@pytest.mark.parametrize("snippet", [
    "import app.services.replica_target_screening\n",
    "from app.services.site_target_evidence_review import review_site_target_evidence\n",
    "from app.services import replica_target_screening\n",
    "from .replica_target_screening import screen_replica_read_target\n",
    "from . import site_target_evidence_review\n",
    "importlib.import_module('app.services.replica_target_screening')\n",
    "__import__('app.services.site_target_evidence_review')\n",
])
def test_guard_catches_common_unreviewed_import_forms(snippet: str) -> None:
    assert _draft_reference_lines(snippet, in_services=True) == [1]


def test_guard_does_not_confuse_normal_existing_read_adapter_import() -> None:
    text = (
        "from app.adapters.demis.factory import create_readonly_demis_adapter\n"
        "from app.services.execution_eligibility import evaluate_execution_eligibility\n"
    )
    assert _draft_reference_lines(text, in_services=True) == []


def test_tests_and_docs_are_not_runtime_authorization_sources() -> None:
    """Only app source is scanned; a passing test never issues site approval."""
    assert all(path.is_relative_to(APP_ROOT) for path in EXCLUDED_FROM_SCAN)
    assert len(EXCLUDED_FROM_SCAN) == 2
    for path in EXCLUDED_FROM_SCAN:
        assert path.exists()
    assert (APP_ROOT / "services" / "execution_eligibility.py").exists()
