# Structured Query Plan (Phase 29-B)

## Purpose

Phase 29-B defines the **Structured Query Plan** contract and deterministic
validator for Dynamic Query Path B. Callers (future MCP/Web) submit a logical
plan — never SQL. DQA validates the plan against:

1. one Active Catalog revision snapshot
2. an explicit Semantic Resource mapping (Phase 29-A)

This PR delivers:

- strict `StructuredQueryPlan` Pydantic contracts (`extra="forbid"`)
- enum operators, typed filter values, bounded collections/limit
- deterministic validation producing an immutable `ValidatedLogicalPlan`
- focused documentation and tests

It does **not** deliver:

- SQL compiler (Phase 29-C)
- Dynamic Query execution / DEMIS access (Phase 29-D)
- MCP tools, Web APIs, or UI
- semantic mapping approval/persistence
- Alembic migrations

## Trust boundary

| Layer | Authority |
|-------|-----------|
| Active Catalog revision | Physical schema truth |
| Explicit Semantic Resource mapping | Candidate logical bindings only |
| Future mapping approval workflow | Required before production Dynamic Query execution |
| ValidatedLogicalPlan (29-B) | **Validation-only** — not approved, not executable |
| LLM / name heuristics | Never used to infer resources, fields, or joins |

Rules:

1. Default Semantic Resource registry is empty → plan status `NOT_CONFIGURED`.
2. Test-only injected mappings may be used for contract validation.
3. Mapping `VALID` status alone does **not** imply approval or executability.
4. Every `ValidatedLogicalPlan` sets `validation_only=true`, `executable=false`,
   `approved=false`.
5. No SQL text, expression ASTs, or execution tokens are produced.

## Plan contract

Format version: `plan_format_version = "1.0.0"`
(`app.domain.structured_query_plan.PLAN_FORMAT_VERSION`).

| Field | Role |
|-------|------|
| `source_name` | Active Catalog / mapping source |
| `resource_key` | Primary logical resource |
| `select` | Logical field keys (SELECT capability) |
| `filters` | Typed predicates (FILTER capability) |
| `sort` | Sort specs (SORT capability) |
| `group_by` | Group fields (GROUP_BY capability) |
| `aggregations` | Aggregation specs (AGGREGATE capability) |
| `relationships` | Optional explicit relationship keys for joins |
| `limit` | Bounded row limit (`1..1000`) |

Forbidden in the contract:

- arbitrary SQL / expression fields
- caller-supplied join condition text
- undeclared extra keys (`extra="forbid"`)

### Filter operators

`EQ`, `NE`, `LT`, `LE`, `GT`, `GE`, `IN`, `NOT_IN`, `BETWEEN`, `LIKE`,
`IS_NULL`, `IS_NOT_NULL` — allowed set depends on normalized logical data type
(`integer`, `number`, `string`, `boolean`, `date`, `datetime`).

Value rules:

- `date`: exactly `YYYY-MM-DD` (compact/week-date forms rejected); impossible
  calendar dates rejected; normalized to `YYYY-MM-DD`
- `datetime`: ISO-8601 datetime with an explicit time component; normalized via
  `datetime.isoformat()`
- `number`: finite values only (`NaN` / `±Infinity` / float-overflow ints rejected)
- `IN` / `BETWEEN` lists are stored as immutable tuples (JSON arrays on dump)

### Aggregations

`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`. `SUM`/`AVG` require numeric logical types.
When aggregations are present, every `select` field must appear in `group_by`,
and every `sort` field must also appear in `group_by`.
`group_by` without aggregations is rejected.

### Complexity bounds

| Bound | Max |
|-------|-----|
| select fields | 32 |
| filters | 16 |
| sort specs | 8 |
| group_by fields | 8 |
| aggregations | 8 |
| relationships | 4 |
| IN list size | 50 |
| string value length | 512 |
| limit | 1000 |

## Validation statuses

| Status | Meaning |
|--------|---------|
| `NOT_CONFIGURED` | No semantic mapping for source (default runtime) |
| `STALE` | Semantic mapping stale vs Active Catalog |
| `INVALID` | Structural/capability/type/operator/complexity/forbidden-input failure, or invalid mapping |
| `VALID` | Plan consistent with Catalog + mapping; still **not** executable authority |

## Compatibility

- Reuses Phase 29-A Semantic Resource resolver/registry unchanged
- Preserves Phase 27 Discovery and Phase 28 MCP/Web Template execution
- No new executable SQL surface

## Future boundary (not in 29-B)

- Deterministic SQL compiler (29-C)
- Shared Dynamic Query execution + audit (29-D)
- Mapping approval/persistence enabling production Path B
