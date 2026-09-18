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

Editing an approved template should create a new version requiring approval.

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
