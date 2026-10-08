# Deterministic Query Compiler (Phase 29-C)

## Purpose

Phase 29-C compiles a **server-revalidated** Structured Query Plan into a
preview-only Oracle `SELECT` statement plus a separate bind-parameter map.

Input path:

```text
StructuredQueryPlan
  → validate_structured_query_plan (29-B; Active Catalog + Semantic Mapping)
  → deterministic Oracle SELECT compiler
  → CompiledQueryResult (SQL text + binds)
  → validate_sql_safety (existing AST allowlist)
```

This PR does **not** deliver:

- DEMIS execution / credentials / connection opening
- MCP tools, Web APIs, or UI
- mapping approval/persistence
- execution tokens
- runtime enablement of Dynamic Query Path B
- Alembic migrations

The existing Template Query execution path is unchanged.

## Trust boundary

| Artifact | Authority |
|----------|-----------|
| Active Catalog revision | Physical schema/tables/columns/FKs |
| Explicit Semantic Resource mapping | Candidate logical bindings (not approval) |
| Caller `StructuredQueryPlan` | Untrusted input; always revalidated |
| Caller-supplied `ValidatedLogicalPlan` | **Not accepted** as compiler input |
| `CompiledQueryResult` | Preview-only (`approved=false`, `executable=false`) |

Rules:

1. Default empty Semantic Resource registry → `NOT_CONFIGURED` (fail closed).
2. Stale/invalid mappings fail closed; no SQL is emitted.
3. Physical identifiers come only from validated Catalog bindings.
4. Caller filter values are never concatenated into SQL text — only named binds.
5. Compiled SQL must pass `validate_sql_safety` before a `VALID` result is returned.
6. Mapping/plan validity alone does not imply production approval or executability.

## Compiler contract

Entry point: `compile_structured_query_plan(session, plan, *, registry=None)`.

### Output (`CompiledQueryResult`)

| Field | Role |
|-------|------|
| `sql_text` | Single Oracle `SELECT` (or `null` on failure) |
| `bind_parameters` | `{name: value}` map; values never appear in SQL |
| `catalog_revision_id` / `schema_fingerprint` / `mapping_version` | Provenance |
| `sql_safety` | Report from the existing SQL safety validator |
| `preview_only` / `validation_only` | Always `true` |
| `approved` / `executable` | Always `false` |

Identical validated inputs produce identical SQL text and bind names/order.

### SQL shape

- Explicit column projection (never `SELECT *`)
- Primary table alias `t0`; joined targets `t1..tn` in relationship order
- `INNER JOIN ... ON` built only from explicit relationship keys and exact
  Catalog FK column mappings (supports composite keys)
- Filters: `=`, `<>`, `<`, `<=`, `>`, `>=`, `LIKE`, `IN`, `NOT IN`, `BETWEEN`,
  `IS NULL`, `IS NOT NULL`
- Aggregations: `COUNT` / `SUM` / `AVG` / `MIN` / `MAX`
- Bounded rows via outer `WHERE ROWNUM <= :p_limit` (literal bind; not inlined)
- Identifiers double-quoted after strict Oracle identifier validation

### Limitations

- Fields/filters/sorts compile against the **primary** resource only
- Relationships produce joins but do not yet project related-resource fields
- Oracle dialect only (aligned with current SQL safety dialect isolation)
- No subqueries beyond the ROWNUM wrapper, no UNION/CTE/DML/DDL/procedures
- No Dynamic Query execution enablement (Phase 29-D)

## Compatibility

- Reuses Phase 29-A Semantic Resource registry/resolver
- Reuses Phase 29-B plan validation (always)
- Reuses existing `validate_sql_safety` allowlist
- Preserves Phase 28 Template Query MCP/Web execution unchanged
