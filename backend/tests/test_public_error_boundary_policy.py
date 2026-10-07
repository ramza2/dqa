"""Static regression guard for public API error-boundary policy.

Route code must not directly stringify typed exceptions or feed typed-exception
state into FastAPI HTTPException.detail. Reviewed public contracts should go
through the shared public-error mapper instead.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROUTES_DIR = Path(__file__).resolve().parents[1] / "app" / "api" / "routes"


def _root_name(node: ast.AST) -> str | None:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _referenced_names(node: ast.AST) -> set[str]:
    return {item.id for item in ast.walk(node) if isinstance(item, ast.Name)}


def _annotation_text(annotation: ast.AST | None) -> str:
    if annotation is None:
        return ""
    try:
        return ast.unparse(annotation)
    except Exception:
        return ""


def _exception_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = {
        arg.arg
        for arg in (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
        if "Error" in _annotation_text(arg.annotation)
    }
    if function.args.vararg is not None and "Error" in _annotation_text(
        function.args.vararg.annotation
    ):
        names.add(function.args.vararg.arg)
    if function.args.kwarg is not None and "Error" in _annotation_text(
        function.args.kwarg.annotation
    ):
        names.add(function.args.kwarg.arg)

    for node in ast.walk(function):
        if isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
    return names


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _is_exception_class_name(node: ast.AST, exception_names: set[str]) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "__name__"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "__class__"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id in exception_names
    )


def _scan_source(source: str, *, filename: str) -> list[str]:
    tree = ast.parse(source, filename=filename)
    violations: list[str] = []

    for function in (
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ):
        exception_names = _exception_names(function)
        if not exception_names:
            continue

        for node in ast.walk(function):
            if isinstance(node, ast.Attribute):
                if (
                    node.attr == "message"
                    and isinstance(node.value, ast.Attribute)
                    and node.value.attr == "issue"
                    and _root_name(node) in exception_names
                ):
                    violations.append(
                        f"{filename}:{node.lineno}: typed exception .issue.message passthrough"
                    )

            if isinstance(node, ast.Call) and _call_name(node) in {"str", "repr"}:
                if any(
                    _referenced_names(arg) & exception_names
                    for arg in node.args
                ):
                    violations.append(
                        f"{filename}:{node.lineno}: typed exception stringification"
                    )

            if isinstance(node, ast.JoinedStr):
                unsafe_interpolation = any(
                    isinstance(value, ast.FormattedValue)
                    and _referenced_names(value.value) & exception_names
                    and not _is_exception_class_name(value.value, exception_names)
                    for value in node.values
                )
                if unsafe_interpolation:
                    violations.append(
                        f"{filename}:{node.lineno}: typed exception interpolation"
                    )

            if isinstance(node, ast.Call) and _call_name(node) == "HTTPException":
                detail = next(
                    (kw.value for kw in node.keywords if kw.arg == "detail"),
                    None,
                )
                if detail is not None and _referenced_names(detail) & exception_names:
                    violations.append(
                        f"{filename}:{node.lineno}: typed exception used in HTTPException.detail"
                    )

    return violations


def test_route_public_error_boundaries_do_not_passthrough_typed_exceptions() -> None:
    violations: list[str] = []
    for path in sorted(ROUTES_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        violations.extend(
            _scan_source(path.read_text(encoding="utf-8"), filename=str(path))
        )

    assert not violations, "\n".join(violations)


def test_policy_guard_detects_common_exception_leak_patterns() -> None:
    insecure = """
from fastapi import HTTPException

class DomainError(Exception):
    pass

def mapper(exc: DomainError):
    a = str(exc)
    b = f"failure: {exc}"
    c = exc.issue.message
    raise HTTPException(
        status_code=500,
        detail={"code": exc.code, "message": c, "debug": a + b},
    )
"""
    violations = _scan_source(insecure, filename="synthetic_insecure_route.py")

    assert any(".issue.message passthrough" in item for item in violations)
    assert any("stringification" in item for item in violations)
    assert any("interpolation" in item for item in violations)
    assert any("HTTPException.detail" in item for item in violations)


def test_policy_guard_allows_reviewed_public_error_mapper_usage() -> None:
    secure = """
class DomainError(Exception):
    pass

def mapper(exc: DomainError):
    return build_public_http_error(
        error_code=exc.code,
        contracts=PUBLIC_ERRORS,
        fallback_code="DOMAIN_INTERNAL_ERROR",
        fallback_status_code=500,
        fallback_message="domain operation failed",
    )
"""
    assert _scan_source(secure, filename="synthetic_secure_route.py") == []
