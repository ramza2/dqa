import type {
  CatalogRelationItem,
  DirectedRelation,
} from "../types/catalog";

function relationKey(item: CatalogRelationItem, direction: "OUT" | "IN"): string {
  return [
    direction,
    item.name ?? "",
    item.schema_name ?? "",
    item.table_name,
    item.referenced_schema_name ?? "",
    item.referenced_table_name,
  ].join("|");
}

/**
 * Merge outgoing (source table) and incoming (referenced table) relation lists.
 *
 * Backend incoming filter only supports `referenced_table_name` (no referenced schema).
 * Callers should optionally filter incoming rows to the selected schema_name.
 */
export function mergeDirectedRelations(
  outgoing: CatalogRelationItem[],
  incoming: CatalogRelationItem[],
  selectedSchema: string,
): DirectedRelation[] {
  const merged = new Map<string, DirectedRelation>();

  for (const item of outgoing) {
    const key = relationKey(item, "OUT");
    merged.set(key, {
      direction: "OUT",
      key,
      name: item.name,
      sourceSchema: item.schema_name,
      sourceTable: item.table_name,
      targetSchema: item.referenced_schema_name,
      targetTable: item.referenced_table_name,
      columns: item.columns,
    });
  }

  for (const item of incoming) {
    // Contract limitation: no referenced_schema filter on the API.
    if (item.referenced_schema_name && item.referenced_schema_name !== selectedSchema) {
      continue;
    }
    const key = relationKey(item, "IN");
    if (merged.has(key)) {
      continue;
    }
    // Also skip if an OUT entry already covers the same constraint identity.
    const outIdentity = [
      "OUT",
      item.name ?? "",
      item.schema_name ?? "",
      item.table_name,
      item.referenced_schema_name ?? "",
      item.referenced_table_name,
    ].join("|");
    if (merged.has(outIdentity)) {
      continue;
    }
    merged.set(key, {
      direction: "IN",
      key,
      name: item.name,
      sourceSchema: item.schema_name,
      sourceTable: item.table_name,
      targetSchema: item.referenced_schema_name,
      targetTable: item.referenced_table_name,
      columns: item.columns,
    });
  }

  return Array.from(merged.values()).sort((a, b) => {
    const left = `${a.direction}|${a.name ?? ""}|${a.sourceTable}|${a.targetTable}`;
    const right = `${b.direction}|${b.name ?? ""}|${b.sourceTable}|${b.targetTable}`;
    return left.localeCompare(right);
  });
}

export function formatColumnMapping(
  columns: { column: string; referenced_column: string }[],
): string {
  if (columns.length === 0) {
    return "—";
  }
  return columns.map((c) => `${c.column} → ${c.referenced_column}`).join(", ");
}
