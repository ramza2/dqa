"""Deterministic SQL Safety Validator for Query Template SQL (no execution).

Uses sqlglot (Oracle dialect for current Oracle-style named binds) with an AST
allowlist. Dialect choice is isolated here so Connection Profile / DEMIS DBMS
selection can later switch the reader without scattering Oracle checks.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from sqlglot import exp, parse
from sqlglot.dialects.oracle import Oracle
from sqlglot.errors import ParseError, TokenError
from sqlglot.tokens import Token, TokenType

from app.adapters.catalog.sql_safety_codes import SqlSafetyIssueCode
from app.schemas.query_template import QueryTemplateParameter
from app.schemas.sql_safety import SqlSafetyIssue, SqlSafetyReport

# Isolated dialect for current Oracle-style templates. Not a global DEMIS commitment.
_SQL_DIALECT = "oracle"

_FORBIDDEN_ROOT_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,
    exp.Commit,
    exp.Rollback,
    exp.Set,
    exp.Transaction,
    exp.Use,
    exp.Copy,
    exp.Analyze,
    exp.Refresh,
    exp.Attach,
    exp.Detach,
    exp.Pragma,
    exp.Kill,
)

# Optional classes depending on sqlglot version.
for _name in ("Revoke", "RenameTable", "RenameColumn", "Call", "Execute"):
    _cls = getattr(exp, _name, None)
    if isinstance(_cls, type) and issubclass(_cls, exp.Expression):
        _FORBIDDEN_ROOT_TYPES = (*_FORBIDDEN_ROOT_TYPES, _cls)

_NESTED_WRITE_TYPES: tuple[type[exp.Expression], ...] = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Create,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,
)

for _name in ("Revoke", "Call", "Execute"):
    _cls = getattr(exp, _name, None)
    if isinstance(_cls, type) and issubclass(_cls, exp.Expression):
        _NESTED_WRITE_TYPES = (*_NESTED_WRITE_TYPES, _cls)

# Parents that may host a named value bind (:param).
_VALUE_BIND_PARENT_NAMES = (
    "EQ",
    "NEQ",
    "GT",
    "GTE",
    "LT",
    "LTE",
    "Like",
    "ILike",
    "In",
    "Between",
    "Is",
    "Add",
    "Sub",
    "Mul",
    "Div",
    "Mod",
    "And",
    "Or",
    "Not",
    "Anonymous",
    "Func",
    "Cast",
    "TryCast",
    "Case",
    "If",
    "Coalesce",
    "Nullif",
    "Concat",
    "DPipe",
    "Paren",
    "Alias",
    "Ordered",
    "Window",
    "Where",
    "Having",
    "Group",
    "Limit",
    "Offset",
    "PropertyEQ",
    "JSONExtract",
    "Dot",
    "AtTimeZone",
    "Extract",
    "Substring",
    "Trim",
    "Lower",
    "Upper",
    "Count",
    "Sum",
    "Avg",
    "Min",
    "Max",
)


def _value_bind_parents() -> tuple[type[exp.Expression], ...]:
    parents: list[type[exp.Expression]] = []
    for name in _VALUE_BIND_PARENT_NAMES:
        cls = getattr(exp, name, None)
        if isinstance(cls, type) and issubclass(cls, exp.Expression):
            parents.append(cls)
    # Include Func subclasses broadly via Runtime check in validator.
    return tuple(parents)


_VALUE_BIND_PARENTS = _value_bind_parents()


def validate_sql_safety(
    sql_text: str,
    parameter_schema: Sequence[QueryTemplateParameter] | Sequence[dict[str, Any]] | None = None,
) -> SqlSafetyReport:
    """Validate one SQL text against the read-only Query Template safety policy."""
    declared = _declared_parameter_names(parameter_schema)
    issues: list[SqlSafetyIssue] = []

    if not isinstance(sql_text, str) or not sql_text.strip():
        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.PARSE_ERROR,
                message="sql_text must not be blank",
            )
        )
        return SqlSafetyReport(
            safe=False,
            statement_count=0,
            referenced_parameters=[],
            declared_parameters=declared,
            issues=_dedupe_issues(issues),
        )

    issues.extend(_scan_forbidden_placeholder_tokens(sql_text))

    try:
        expressions = parse(sql_text, read=_SQL_DIALECT)
    except (ParseError, TokenError, ValueError) as exc:
        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.PARSE_ERROR,
                message=f"SQL could not be parsed safely: {type(exc).__name__}",
            )
        )
        return SqlSafetyReport(
            safe=False,
            statement_count=0,
            referenced_parameters=[],
            declared_parameters=declared,
            issues=_dedupe_issues(issues),
        )

    # Drop empty trailing None entries sqlglot may emit for whitespace-only tails.
    statements = [node for node in expressions if node is not None]
    statement_count = len(statements)

    if statement_count == 0:
        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.PARSE_ERROR,
                message="SQL produced no parseable statements",
            )
        )
        return SqlSafetyReport(
            safe=False,
            statement_count=0,
            referenced_parameters=[],
            declared_parameters=declared,
            issues=_dedupe_issues(issues),
        )

    if statement_count != 1:
        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.MULTIPLE_STATEMENTS,
                message=f"exactly one SQL statement is allowed; found {statement_count}",
            )
        )

    referenced: list[str] = []
    for node in statements:
        issues.extend(_validate_statement(node))
        referenced.extend(_named_placeholders(node))

    referenced_unique = _unique_preserve_order(referenced)
    issues.extend(_match_parameters(declared, referenced_unique))

    ordered_issues = _dedupe_issues(issues)
    return SqlSafetyReport(
        safe=len(ordered_issues) == 0,
        statement_count=statement_count,
        referenced_parameters=referenced_unique,
        declared_parameters=declared,
        issues=ordered_issues,
    )


def require_sql_safe(
    sql_text: str,
    parameter_schema: Sequence[QueryTemplateParameter] | Sequence[dict[str, Any]] | None = None,
) -> SqlSafetyReport:
    """Return the safety report; intended as the future execution-gate helper."""
    return validate_sql_safety(sql_text, parameter_schema)


def _validate_statement(node: exp.Expression) -> list[SqlSafetyIssue]:
    issues: list[SqlSafetyIssue] = []

    if isinstance(node, exp.Command):
        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED,
                message=f"command statement is not allowed: {node.name or node.this}",
            )
        )
        return issues

    if isinstance(node, _FORBIDDEN_ROOT_TYPES) and not isinstance(node, exp.Select):
        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED,
                message=f"statement type is not allowed: {type(node).__name__}",
            )
        )
        return issues

    if not isinstance(node, exp.Select):
        # Unknown / unsupported top-level — fail closed.
        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.STATEMENT_NOT_ALLOWED,
                message=f"unsupported top-level statement: {type(node).__name__}",
            )
        )
        return issues

    # Nested writes (including writable CTEs) — scan whole AST.
    for write in node.find_all(*_NESTED_WRITE_TYPES):
        if write is node:
            continue
        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.FORBIDDEN_CONSTRUCT,
                message=f"nested non-read-only construct is forbidden: {type(write).__name__}",
            )
        )

    for select in node.find_all(exp.Select):
        locks = select.args.get("locks") or []
        if locks:
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.FOR_UPDATE_FORBIDDEN,
                    message="SELECT ... FOR UPDATE (locking) is forbidden",
                )
            )
        if select.args.get("into") is not None:
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.SELECT_INTO_FORBIDDEN,
                    message="SELECT ... INTO is forbidden",
                )
            )

    # CTE bodies must themselves be read-only Select.
    for cte in node.find_all(exp.CTE):
        body = cte.this
        if body is None:
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.FORBIDDEN_CONSTRUCT,
                    message="CTE body is missing",
                )
            )
            continue
        if not isinstance(body, exp.Select):
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.FORBIDDEN_CONSTRUCT,
                    message=f"CTE body must be SELECT; found {type(body).__name__}",
                )
            )

    issues.extend(_validate_placeholder_contexts(node))
    return issues


def _validate_placeholder_contexts(node: exp.Expression) -> list[SqlSafetyIssue]:
    issues: list[SqlSafetyIssue] = []
    for placeholder in node.find_all(exp.Placeholder):
        name = placeholder.name if placeholder.name else None
        if not name:
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                    message="positional placeholders (e.g. ?) are forbidden",
                )
            )
            continue
        if name.isdigit():
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                    message=f"positional placeholder :{name} is forbidden",
                )
            )
            continue

        parent = placeholder.parent
        if parent is None:
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.DYNAMIC_IDENTIFIER_FORBIDDEN,
                    message=f"bind :{name} has no valid value context",
                )
            )
            continue

        if isinstance(parent, (exp.Table, exp.Schema, exp.Column, exp.Identifier)):
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.DYNAMIC_IDENTIFIER_FORBIDDEN,
                    message=f"bind :{name} cannot be used as a dynamic object identifier",
                )
            )
            continue

        # Direct SELECT projection of a bare bind is treated as identifier substitution.
        if isinstance(parent, exp.Select) and placeholder in list(parent.expressions):
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.DYNAMIC_IDENTIFIER_FORBIDDEN,
                    message=(
                        f"bind :{name} cannot be used as a selected object/column identifier"
                    ),
                )
            )
            continue

        if isinstance(parent, exp.Alias) and parent.this is placeholder:
            # SELECT :x AS alias — still a bare projection of a bind.
            grand = parent.parent
            if isinstance(grand, exp.Select) and parent in list(grand.expressions):
                issues.append(
                    SqlSafetyIssue(
                        code=SqlSafetyIssueCode.DYNAMIC_IDENTIFIER_FORBIDDEN,
                        message=(
                            f"bind :{name} cannot be used as a selected object/column identifier"
                        ),
                    )
                )
                continue

        if isinstance(parent, _VALUE_BIND_PARENTS) or isinstance(parent, exp.Func):
            continue

        issues.append(
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.DYNAMIC_IDENTIFIER_FORBIDDEN,
                message=(
                    f"bind :{name} appears in unsupported context "
                    f"{type(parent).__name__}"
                ),
            )
        )
    return issues


def _named_placeholders(node: exp.Expression) -> list[str]:
    names: list[str] = []
    for placeholder in node.find_all(exp.Placeholder):
        name = placeholder.name
        if name and not name.isdigit():
            names.append(name)
    return names


def _declared_parameter_names(
    parameter_schema: Sequence[QueryTemplateParameter] | Sequence[dict[str, Any]] | None,
) -> list[str]:
    if not parameter_schema:
        return []
    names: list[str] = []
    for item in parameter_schema:
        if isinstance(item, QueryTemplateParameter):
            names.append(item.name)
        elif isinstance(item, dict):
            raw = item.get("name")
            if isinstance(raw, str) and raw:
                names.append(raw)
    return _unique_preserve_order(names)


def _match_parameters(
    declared: Sequence[str], referenced: Sequence[str]
) -> list[SqlSafetyIssue]:
    issues: list[SqlSafetyIssue] = []
    declared_map = {name.casefold(): name for name in declared}
    referenced_map = {name.casefold(): name for name in referenced}

    for key, canonical in referenced_map.items():
        if key not in declared_map:
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.UNDECLARED_PARAMETER,
                    message=f"SQL references undeclared parameter :{canonical}",
                )
            )

    for key, canonical in declared_map.items():
        if key not in referenced_map:
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.UNUSED_DECLARED_PARAMETER,
                    message=f"declared parameter '{canonical}' is not referenced in SQL",
                )
            )
    return issues


def _scan_forbidden_placeholder_tokens(sql_text: str) -> list[SqlSafetyIssue]:
    """Lexical scan (outside strings/comments) for unsupported placeholder shapes."""
    issues: list[SqlSafetyIssue] = []
    try:
        tokens = list(Oracle.Tokenizer().tokenize(sql_text))
    except TokenError as exc:
        return [
            SqlSafetyIssue(
                code=SqlSafetyIssueCode.PARSE_ERROR,
                message=f"SQL tokenizer failed: {type(exc).__name__}",
            )
        ]

    i = 0
    while i < len(tokens):
        token = tokens[i]
        # Skip string/comment-like payloads (sqlglot does not emit comment tokens
        # into the token stream for '--' comments already stripped).
        if token.token_type in {TokenType.STRING, TokenType.NUMBER}:
            # NUMBER alone is fine; :1 is COLON + NUMBER.
            i += 1
            continue

        if token.token_type == TokenType.PLACEHOLDER:
            issues.append(
                SqlSafetyIssue(
                    code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                    message="positional placeholders (e.g. ?) are forbidden",
                )
            )
            i += 1
            continue

        if token.token_type == TokenType.COLON:
            nxt = _next_token(tokens, i + 1)
            if nxt is not None and nxt.token_type == TokenType.NUMBER:
                issues.append(
                    SqlSafetyIssue(
                        code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                        message="positional placeholders (e.g. :1) are forbidden",
                    )
                )
            i += 1
            continue

        if token.token_type == TokenType.VAR and token.text.startswith("$"):
            rest = token.text[1:]
            if rest.isdigit() or token.text == "$":
                # `$1` as a single VAR, or bare `$` before `{name}`.
                if rest.isdigit():
                    issues.append(
                        SqlSafetyIssue(
                            code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                            message="positional placeholders (e.g. $1) are forbidden",
                        )
                    )
                else:
                    # Look ahead for ${name}
                    if _match_seq(
                        tokens,
                        i,
                        (TokenType.VAR, TokenType.L_BRACE, TokenType.VAR, TokenType.R_BRACE),
                    ):
                        issues.append(
                            SqlSafetyIssue(
                                code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                                message="template placeholders (e.g. ${name}) are forbidden",
                            )
                        )
            i += 1
            continue

        if token.token_type == TokenType.L_BRACE:
            if _match_seq(
                tokens,
                i,
                (
                    TokenType.L_BRACE,
                    TokenType.L_BRACE,
                    TokenType.VAR,
                    TokenType.R_BRACE,
                    TokenType.R_BRACE,
                ),
            ):
                issues.append(
                    SqlSafetyIssue(
                        code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                        message="template placeholders (e.g. {{name}}) are forbidden",
                    )
                )
            i += 1
            continue

        if token.token_type == TokenType.MOD:
            # %s or %(name)s
            if _match_seq(tokens, i, (TokenType.MOD, TokenType.VAR)) and tokens[
                i + 1
            ].text.casefold() == "s":
                issues.append(
                    SqlSafetyIssue(
                        code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                        message="printf-style placeholders (e.g. %s) are forbidden",
                    )
                )
            elif _match_seq(
                tokens,
                i,
                (
                    TokenType.MOD,
                    TokenType.L_PAREN,
                    TokenType.VAR,
                    TokenType.R_PAREN,
                    TokenType.VAR,
                ),
            ) and tokens[i + 4].text.casefold() == "s":
                issues.append(
                    SqlSafetyIssue(
                        code=SqlSafetyIssueCode.POSITIONAL_PARAMETER_FORBIDDEN,
                        message="printf-style placeholders (e.g. %(name)s) are forbidden",
                    )
                )
            i += 1
            continue

        i += 1

    return issues


def _next_token(tokens: Sequence[Token], index: int) -> Token | None:
    if index < len(tokens):
        return tokens[index]
    return None


def _match_seq(
    tokens: Sequence[Token], start: int, expected: Sequence[TokenType]
) -> bool:
    if start + len(expected) > len(tokens):
        return False
    return all(tokens[start + offset].token_type == token_type for offset, token_type in enumerate(expected))


def _unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _dedupe_issues(issues: Sequence[SqlSafetyIssue]) -> list[SqlSafetyIssue]:
    """Stable, deterministic issue ordering by (code, message)."""
    unique: list[SqlSafetyIssue] = []
    seen: set[tuple[str, str]] = set()
    for issue in issues:
        key = (issue.code, issue.message)
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return sorted(unique, key=lambda item: (item.code, item.message))
