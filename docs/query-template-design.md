# Query Template Design

## 1. Objective

Query Templates are the only executable SQL source in DQA.

Natural language and LLM output may select a template and propose parameters, but they do not create executable arbitrary SQL.

## 2. Lifecycle

```text
DRAFT
  |
  v
IN_REVIEW
  |
  +--> REJECTED
  |
  v
APPROVED
  |
  +--> DISABLED
  |
  v
EXECUTABLE
```

A template is executable only when:
- latest intended version is APPROVED
- enabled = true
- compatible with the active Catalog
- bound to an enabled compatible Connection Profile
- deterministic SQL validation passes

Editing an approved or rejected template must create a **new DRAFT version**.
Never mutate an `IN_REVIEW`, `APPROVED`, or `REJECTED` version in place, and never
transition those statuses back to `DRAFT`.

Allowed status transitions for a single version:

```text
DRAFT -> IN_REVIEW
IN_REVIEW -> APPROVED
IN_REVIEW -> REJECTED
```

`APPROVED` and `REJECTED` are terminal for that version.

Stable template metadata (`name`, `description`, `target_schemas`) may be edited
only while the template has never entered review. After any version reaches
`IN_REVIEW` / `APPROVED` / `REJECTED`, those stable fields are frozen; further
semantic changes require a new QueryTemplate. Version authoring fields
(`sql_text`, `parameter_schema`, `row_limit`, `timeout_seconds`) remain editable
on a later DRAFT version.

`APPROVED` means workflow approval only. It does **not** mean SQL safety passed
or that the template is executable.

`enabled=true` is an operational candidacy flag only. Execution still requires
later gates (SQL safety validator, Connection Profile, RBAC, Active Catalog
compatibility, read-only adapter). Approval never auto-enables a template.

Review transitions append `QueryTemplateReviewEvent` rows (append-only).
`approved_by` / review `actor` remain nullable until Authentication/RBAC lands.

## 3. Suggested model

### QueryTemplate

- id
- stable_key
- name
- description
- source_key
- target_schemas
- current_version_id
- enabled
- created_at
- updated_at

### QueryTemplateVersion

- id
- template_id
- version
- sql_text
- parameter_schema
- row_limit
- timeout_seconds
- catalog_fingerprint_constraint
- approval_status
- created_by
- created_at
- approved_by
- approved_at
- approval_note

### Parameter definition

Each parameter should support:
- name
- label
- description
- type
- required
- default when safe
- allowed values or pattern
- min/max constraints
- list size constraints
- sensitive flag

Initial types:
- string
- integer
- decimal
- boolean
- date
- datetime
- enum
- string_list
- integer_list

## 4. SQL authoring rules

Templates must:
- contain one statement
- be SELECT-only, including WITH ... SELECT when the final statement is read-only
- reject SELECT ... FOR UPDATE
- reject SELECT ... INTO or equivalent write/locking forms
- use named bound parameters
- avoid value interpolation
- avoid dynamic object-name substitution from users
- avoid schema/table names supplied as runtime parameters

If multiple query shapes are required, create multiple approved template versions/templates rather than constructing dynamic SQL freely.

### 4.1 SQL Safety Validator

DQA validates template SQL with a deterministic parser/tokenizer + AST allowlist
(`sqlglot`, Oracle dialect isolated for current Oracle-style `:named` binds).

Policy highlights:
- fail-closed on parse/tokenize errors and unsupported top-level commands
- exactly one statement; leading/intermediate empty statements and repeated
  trailing terminators are rejected (tokenizer-based; at most one trailing `;`)
- read-only `SELECT` / `WITH ... SELECT` only (CTE bodies must also be SELECT)
- reject `FOR UPDATE`, `SELECT INTO`, nested DML/DDL, procedural/admin commands
- named bound parameters only (`:name`); reject `?`, `$1`, `:1`, `%s`, `%(name)s`,
  `{{name}}`, `${name}`
- declared `parameter_schema` names must match referenced binds exactly
  (case-insensitive; report uses declared canonical names)
- reject binds used as dynamic schema/table/column identifiers

`validate_sql_safety()` always returns a report (`safe=false` when unsafe).
`require_sql_safe()` is the future execution-gate helper: it returns the report
only when safe, otherwise raises `SqlSafetyValidationError` with the typed
report attached (no full SQL text in the exception message).

`GET /api/v1/query-templates/{id}/sql-safety` uses `validate_sql_safety()` and
returns a fresh report (`safe`, `issues[]` with typed codes), including
HTTP 200 + `safe=false` for unsafe SQL. Results are not persisted.

SQL Safety PASS is independent of approval/enable:
- `APPROVED` ≠ executable
- `enabled=true` ≠ executable
- SQL Safety PASS alone is not an execution permission

Application-side SQL safety is defense-in-depth and does **not** replace a
read-only DEMIS account or least-privilege EXECUTE grants. Syntactic SELECT
may still call DB functions/packages with side effects when privileges allow;
function allowlisting is out of scope for this validator.

## 5. Catalog compatibility

Template validation should resolve referenced tables/columns against the active Catalog where feasible.

At minimum store:
- Catalog source identity
- compatible schema(s)
- fingerprint policy

Possible compatibility modes:
- EXACT_FINGERPRINT
- SOURCE_AND_SCHEMA
- OPERATOR_REVALIDATION_REQUIRED

Initial implementation should prefer conservative compatibility.

## 6. Recommendation

Recommendation pipeline:

```text
User request
  -> retrieve relevant catalog objects
  -> retrieve APPROVED/ENABLED templates
  -> rank candidate templates
  -> return top candidates
  -> extract candidate parameters
  -> deterministic validation
```

A low-confidence result should request clarification rather than invent parameter values.

## 7. Execution preview

Before execution present:
- template name/version
- description
- target source/schema
- parameter values
- row limit
- timeout
- active Catalog fingerprint
- logical Connection Profile / target environment (without secrets)

Do not require users to inspect raw SQL for basic use, but allow authorized operators to view it.

## 8. Audit

Each execution references an immutable Query Template version.

Never audit only the stable template ID without version.


## 9. Result-to-LLM policy

Query result rows, patient identifiers, and sensitive medical fields are not sent to an LLM by default.

If result summarization is introduced later, it requires:
- an approved provider/data-egress policy
- explicit permitted field/data classifications
- deterministic redaction/minimization before the provider call where required
- audit of whether LLM post-processing occurred

Template recommendation and parameter extraction should rely on the user request, Catalog metadata, and template metadata rather than raw query-result rows.
