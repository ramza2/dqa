import type { CatalogRelationColumnMapping, DirectedRelation } from "../types/catalog";

export interface FocusedErdEdge {
  key: string;
  name: string | null;
  direction: "IN" | "OUT";
  neighborSchema: string;
  neighborTable: string;
  columns: CatalogRelationColumnMapping[];
  outsideSchema: boolean;
}
export interface FocusedErdGraph {
  inbound: FocusedErdEdge[];
  outbound: FocusedErdEdge[];
  total: number;
  hidden: number;
  unknown: number;
}

/** One-hop graph from already loaded, revision-checked relations. No DB/API I/O. */
export function buildFocusedErd(
  schema: string,
  table: string,
  relations: DirectedRelation[],
  maxEdges = 40,
): FocusedErdGraph {
  const found: FocusedErdEdge[] = [];
  const seen = new Set<string>();
  let unknown = 0;
  for (const item of relations) {
    const isOut = item.sourceSchema === schema && item.sourceTable === table;
    const isIn = item.targetSchema === schema && item.targetTable === table;
    if (!isOut && !isIn) {
      unknown += 1;
      continue;
    }
    if (!item.sourceSchema || !item.targetSchema || !item.sourceTable || !item.targetTable) {
      unknown += 1;
      continue;
    }
    const direction = isOut ? "OUT" : "IN";
    const neighborSchema = isOut ? item.targetSchema : item.sourceSchema;
    const neighborTable = isOut ? item.targetTable : item.sourceTable;
    const key = [
      direction, item.name ?? "", item.sourceSchema, item.sourceTable,
      item.targetSchema, item.targetTable,
      ...item.columns.map(c => c.column + "=" + c.referenced_column),
    ].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    found.push({
      key,
      name: item.name,
      direction,
      neighborSchema,
      neighborTable,
      columns: item.columns,
      outsideSchema: neighborSchema !== schema,
    });
  }
  found.sort((a, b) => a.key.localeCompare(b.key));
  const limit = Number.isFinite(maxEdges) ? Math.min(40, Math.max(1, Math.trunc(maxEdges))) : 40;
  const visible = found.slice(0, limit);
  return {
    inbound: visible.filter(item => item.direction === "IN"),
    outbound: visible.filter(item => item.direction === "OUT"),
    total: found.length,
    hidden: found.length - visible.length,
    unknown,
  };
}
