import type { CatalogRelationItem, CatalogTableItem } from "../types/catalog";

export interface ErdTable {
  id: string;
  schema: string;
  name: string;
  comment: string | null;
  categories: string[];
}

export interface ErdLink {
  id: string;
  name: string | null;
  source: string;
  target: string;
  mapping: { source: string; target: string }[];
}

export type ErdMode = "full" | "neighborhood" | "category";

export interface ErdSelection {
  mode: ErdMode;
  focus: string;
  category: string;
  search: string;
  hops: 1 | 2;
}

const MAX_VISIBLE_TABLES = 80;
const MAX_VISIBLE_LINKS = 160;

export function tableIdentity(schema: string, name: string): string {
  return JSON.stringify([schema, name]);
}

export function buildCatalogGraph(
  tables: CatalogTableItem[],
  relations: CatalogRelationItem[],
): { nodes: ErdTable[]; links: ErdLink[]; unresolved: number } {
  const nodes = tables.map((table) => ({
    id: tableIdentity(table.schema_name, table.name),
    schema: table.schema_name,
    name: table.name,
    comment: table.comment,
    categories: table.category_ids,
  }));
  const known = new Set(nodes.map((node) => node.id));
  const unique = new Map<string, ErdLink>();
  let unresolved = 0;
  for (const rel of relations) {
    const source = tableIdentity(rel.schema_name ?? "", rel.table_name);
    const target = tableIdentity(rel.referenced_schema_name ?? "", rel.referenced_table_name);
    if (!known.has(source) || !known.has(target)) {
      unresolved += 1;
      continue;
    }
    const mapping = rel.columns.map((item) => ({
      source: item.column,
      target: item.referenced_column,
    }));
    const id = JSON.stringify([source, target, rel.name, mapping]);
    unique.set(id, { id, name: rel.name, source, target, mapping });
  }
  return { nodes, links: [...unique.values()], unresolved };
}

function hopDistances(focus: string, links: ErdLink[], hops: number): Map<string, number> {
  if (!focus) return new Map();
  const adjacent = new Map<string, Set<string>>();
  for (const link of links) {
    if (!adjacent.has(link.source)) adjacent.set(link.source, new Set());
    if (!adjacent.has(link.target)) adjacent.set(link.target, new Set());
    adjacent.get(link.source)!.add(link.target);
    adjacent.get(link.target)!.add(link.source);
  }
  const distances = new Map([[focus, 0]]);
  const queue = [focus];
  for (let i = 0; i < queue.length; i += 1) {
    const current = queue[i];
    const distance = distances.get(current)!;
    if (distance >= hops) continue;
    for (const next of adjacent.get(current) ?? []) {
      if (!distances.has(next)) {
        distances.set(next, distance + 1);
        queue.push(next);
      }
    }
  }
  return distances;
}

/** All filtering/layout limits apply to *already permission-checked* active Catalog metadata. */
export function selectErdGraph(
  graph: ReturnType<typeof buildCatalogGraph>,
  selection: ErdSelection,
) {
  const distances = selection.mode === "neighborhood"
    ? hopDistances(selection.focus, graph.links, selection.hops) : new Map<string, number>();
  const search = selection.search.trim().toLocaleLowerCase();
  const matching = graph.nodes.filter((node) => {
    if (selection.mode === "neighborhood" && !distances.has(node.id)) return false;
    if (selection.mode === "category" && !node.categories.includes(selection.category)) return false;
    if (search && !`${node.schema} ${node.name} ${node.comment ?? ""}`.toLocaleLowerCase().includes(search)) {
      return false;
    }
    return true;
  });
  const degree = new Map(graph.nodes.map((node) => [node.id, 0]));
  for (const link of graph.links) {
    degree.set(link.source, (degree.get(link.source) ?? 0) + 1);
    degree.set(link.target, (degree.get(link.target) ?? 0) + 1);
  }
  const ordered = [...matching].sort((a, b) => {
    if (selection.mode === "neighborhood") {
      const distance = (distances.get(a.id) ?? 3) - (distances.get(b.id) ?? 3);
      if (distance !== 0) return distance;
    }
    return (degree.get(b.id) ?? 0) - (degree.get(a.id) ?? 0)
      || `${a.schema}.${a.name}`.localeCompare(`${b.schema}.${b.name}`);
  });
  const nodes = ordered.slice(0, MAX_VISIBLE_TABLES);
  const visible = new Set(nodes.map((node) => node.id));
  const eligible = new Set(matching.map((node) => node.id));
  const eligibleLinks = graph.links.filter((link) => eligible.has(link.source) && eligible.has(link.target));
  const includedLinks = graph.links.filter((link) => visible.has(link.source) && visible.has(link.target));
  const links = includedLinks.slice(0, MAX_VISIBLE_LINKS);
  return {
    nodes, links, distances,
    hiddenNodes: matching.length - nodes.length,
    hiddenLinks: eligibleLinks.length - links.length,
    totalMatching: matching.length,
  };
}
