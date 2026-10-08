# Semantic Resource Mapping (Phase 29-A)

## Purpose

Phase 29-A defines the **logical resource / field / relationship** contracts that
future Structured Dynamic Query (Path B) will target. MCP and Web callers must
not freeze physical DEMIS schema as the public API.

This PR delivers:

- strict Pydantic/domain contracts
- deterministic validation against **one Active Catalog revision** snapshot
- an injectable read-only registry/resolver (default empty)

It does **not** deliver:

- SQL compiler or Dynamic Query execution
- new MCP tools or Web UI
- persistence / approval workflow for mappings
- hardcoded real DEMIS Patient / Encounter clinical mappings
- Alembic migrations (none required for this bounded scope)

## Trust boundary

| Layer | Authority |
|-------|-----------|
| Active Catalog Package revision | Authoritative for physical schema/tables/columns/FKs |
| Explicit semantic mapping document | Candidate logical bindings only; **not** approved production authority |
| Future approval/persistence workflow | Required before any mapping is trusted for executable Dynamic Query |
| LLM / column-name heuristics | **Never** used to invent clinical meaning or capabilities |

Rules:

1. Default runtime registry is empty → resolution status `NOT_CONFIGURED`.
2. Test injectability is explicit (`SemanticResourceRegistry.from_mapping(...)`).
3. Arbitrary mapping JSON is not an approved authority even if schema-valid.
4. Validation is deterministic application logic against Catalog metadata only.
5. Unknown / unapproved field capabilities are rejected by default.
6. No automatic inference of Patient/Encounter/Lab meaning from physical names.

## Mapping document format

Format version: `mapping_format_version = "1.0.0"` (see
`app.domain.semantic_resource.MAPPING_FORMAT_VERSION`).

Top-level fields:

| Field | Role |
|-------|------|
| `mapping_format_version` | Contract version for this document shape |
| `mapping_version` | Operator/document revision label |
| `source_name` | Must match Active Catalog source |
| `catalog_revision_id` | Must match Active Catalog revision id |
| `schema_fingerprint` | Must match Active Catalog fingerprint |
| `provenance` | Author/note/`review_status` (`UNREVIEWED` / `DRAFT` / `TEST_ONLY`) |
| `resources[]` | Logical resources |

Each resource:

- `resource_key` — stable logical key (e.g. synthetic test keys only in this phase)
- optional `description`
- `physical_table` — `{schema_name, table_name}`
- `fields[]` — logical fields with physical column bindings + capability allowlist
- `relationships[]` — optional bindings to Catalog FK metadata

Each field:

- `field_key`, optional `description`, declared `data_type`
- `physical_column` — `{schema_name, table_name, column_name}`
- `capabilities` — subset of approved allowlist only:
  `SELECT`, `FILTER`, `SORT`, `GROUP_BY`, `AGGREGATE`

Each relationship:

- `relationship_key`, `from_resource_key`, `to_resource_key`
- `catalog_fk` — constraint name, source/target schema+table, ordered column mappings
  that must match Catalog `relations` metadata exactly

## Resolution statuses

| Status | Meaning |
|--------|---------|
| `NOT_CONFIGURED` | No mapping registered for the source (default runtime) |
| `STALE` | Mapping revision id and/or fingerprint does not match Active Catalog (and no other structural errors) |
| `INVALID` | Missing/ambiguous/cross-source refs, duplicate keys, bad FK, unknown capability, unsupported format, or stale mixed with structural errors |
| `VALID` | Explicit mapping fully consistent with the Active Catalog snapshot |

## Compatibility

- Preserves Phase 27 Data Discovery `PHYSICAL` / `LOGICAL` identity kinds.
  `LogicalDiscoveryIdentity` complements `PhysicalDiscoveryIdentity`; Discovery
  search documents remain physical-only in this phase.
- Preserves Phase 28 MCP tools and Web Query Template execution paths.
- No new executable SQL surface.

## Future boundary (not in 29-A)

- Durable storage of mapping documents
- Approval / enablement workflow analogous to Query Templates
- LOGICAL Discovery search-document materialization
- Structured Query Plan validation (29-B; see
  [structured-query-plan.md](structured-query-plan.md)), compiler (29-C),
  execution (29-D)
