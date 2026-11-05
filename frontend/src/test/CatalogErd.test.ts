import { describe, expect, it } from "vitest";
import ELK from "elkjs/lib/elk.bundled.js";
import { buildCatalogGraph, selectErdGraph, tableIdentity } from "../utils/catalogErd";
import type { CatalogRelationItem, CatalogTableItem } from "../types/catalog";

const tables: CatalogTableItem[] = [
  { schema_name: "DEMIS_OWNER", name: "PATIENT", comment: "환자", table_type: "BASE TABLE", category_ids: ["medical"] },
  { schema_name: "DEMIS_OWNER", name: "ENCOUNTER", comment: "진료", table_type: "BASE TABLE", category_ids: ["medical"] },
  { schema_name: "DEMIS_OWNER", name: "PRESCRIPTION", comment: "처방", table_type: "BASE TABLE", category_ids: ["drug"] },
  { schema_name: "OTHER", name: "PATIENT", comment: "동명이 테이블", table_type: "BASE TABLE", category_ids: [] },
];

const relations: CatalogRelationItem[] = [
  { name: "FK_ENC_PT", schema_name: "DEMIS_OWNER", table_name: "ENCOUNTER",
    referenced_schema_name: "DEMIS_OWNER", referenced_table_name: "PATIENT",
    columns: [{ column: "PT_ID", referenced_column: "ID" }] },
  { name: "FK_RX_ENC", schema_name: "DEMIS_OWNER", table_name: "PRESCRIPTION",
    referenced_schema_name: "DEMIS_OWNER", referenced_table_name: "ENCOUNTER",
    columns: [{ column: "ENC_ID", referenced_column: "ID" }] },
  { name: "FK_EXTERNAL", schema_name: "OTHER", table_name: "ABSENT",
    referenced_schema_name: "DEMIS_OWNER", referenced_table_name: "PATIENT", columns: [] },
];

describe("active Catalog ERD graph", () => {
  it("distinguishes same table names in different schemas and omits missing endpoints", () => {
    const graph = buildCatalogGraph(tables, relations);
    expect(graph.nodes).toHaveLength(4);
    expect(graph.links).toHaveLength(2);
    expect(graph.unresolved).toBe(1);
    expect(tableIdentity("DEMIS_OWNER", "PATIENT"))
      .not.toBe(tableIdentity("OTHER", "PATIENT"));
    expect(graph.links[0].mapping).toEqual([{ source: "PT_ID", target: "ID" }]);
  });

  it("supports full, category and focused 1-/2-/3-hop views", () => {
    const extendedTables: CatalogTableItem[] = [
      ...tables,
      { schema_name: "DEMIS_OWNER", name: "LAB", comment: "검사", table_type: "BASE TABLE", category_ids: [] },
    ];
    const extendedRelations: CatalogRelationItem[] = [
      ...relations,
      { name: "FK_LAB_RX", schema_name: "DEMIS_OWNER", table_name: "LAB",
        referenced_schema_name: "DEMIS_OWNER", referenced_table_name: "PRESCRIPTION",
        columns: [{ column: "RX_ID", referenced_column: "ID" }] },
    ];
    const graph = buildCatalogGraph(extendedTables, extendedRelations);
    const selection = { mode: "full" as const, focus: "", category: "", search: "", hops: 1 as const };
    expect(selectErdGraph(graph, selection).nodes).toHaveLength(5);
    expect(selectErdGraph(graph, { ...selection, mode: "category", category: "medical" })
      .nodes.map((node) => node.name).sort()).toEqual(["ENCOUNTER", "PATIENT"]);
    expect(selectErdGraph(graph, { ...selection, search: "처방" }).nodes[0].name)
      .toBe("PRESCRIPTION");
    const center = tableIdentity("DEMIS_OWNER", "PATIENT");
    const hop1 = selectErdGraph(graph, { ...selection, mode: "neighborhood", focus: center });
    expect(hop1.nodes.map((node) => node.name).sort()).toEqual(["ENCOUNTER", "PATIENT"]);
    const hop2 = selectErdGraph(graph, { ...selection, mode: "neighborhood", focus: center, hops: 2 });
    expect(hop2.nodes.map((node) => node.name).sort()).toEqual(["ENCOUNTER", "PATIENT", "PRESCRIPTION"]);
    expect(hop2.distances.get(tableIdentity("DEMIS_OWNER", "PRESCRIPTION"))).toBe(2);
    const hop3 = selectErdGraph(graph, { ...selection, mode: "neighborhood", focus: center, hops: 3 });
    expect(hop3.nodes.map((node) => node.name).sort())
      .toEqual(["ENCOUNTER", "LAB", "PATIENT", "PRESCRIPTION"]);
    expect(hop3.distances.get(tableIdentity("DEMIS_OWNER", "LAB"))).toBe(3);
  });

  it("bounds dense layouts and reports every omitted table and relation", () => {
    const manyTables: CatalogTableItem[] = Array.from({ length: 100 }, (_, index) => ({
      schema_name: "DEMIS_OWNER", name: `TB_${index}`, comment: null,
      table_type: "BASE TABLE", category_ids: [],
    }));
    const manyRelations: CatalogRelationItem[] = Array.from({ length: 220 }, (_, index) => ({
      name: `FK_${index}`,
      schema_name: "DEMIS_OWNER", table_name: "TB_0",
      referenced_schema_name: "DEMIS_OWNER", referenced_table_name: `TB_${index % 80}`,
      columns: [{ column: `SRC_${index}`, referenced_column: "ID" }],
    }));
    const graph = buildCatalogGraph(manyTables, manyRelations);
    const selected = selectErdGraph(graph, { mode: "full", focus: "", category: "", search: "", hops: 1 });
    expect(selected.nodes).toHaveLength(80);
    expect(selected.links).toHaveLength(160);
    expect(selected.hiddenNodes).toBe(20);
    expect(selected.hiddenLinks).toBe(60);
  });

  it("counts relations to layout-omitted nodes as hidden", () => {
    const chainTables: CatalogTableItem[] = Array.from({ length: 90 }, (_, index) => ({
      schema_name: "DEMIS_OWNER", name: `TB_${index}`, comment: null,
      table_type: "BASE TABLE", category_ids: [],
    }));
    const chainRelations: CatalogRelationItem[] = Array.from({ length: 89 }, (_, index) => ({
      name: `FK_${index}`, schema_name: "DEMIS_OWNER", table_name: `TB_${index}`,
      referenced_schema_name: "DEMIS_OWNER", referenced_table_name: `TB_${index + 1}`,
      columns: [],
    }));
    const graph = buildCatalogGraph(chainTables, chainRelations);
    const selection = selectErdGraph(graph, {
      mode: "full", focus: "", category: "", search: "", hops: 1,
    });
    expect(selection.hiddenNodes).toBe(10);
    expect(selection.hiddenLinks).toBe(89 - selection.links.length);
    expect(selection.hiddenLinks).toBeGreaterThan(0);
  });

  it("ELK accepts the schema-qualified node identities and produces orthogonal edge sections", async () => {
    const graph = buildCatalogGraph(tables, relations);
    const result = await new ELK().layout({
      id: "root",
      layoutOptions: { "elk.algorithm": "layered", "elk.edgeRouting": "ORTHOGONAL" },
      children: graph.nodes.map((node) => ({ id: node.id, width: 250, height: 94 })),
      edges: graph.links.map((link, index) => ({
        id: `edge-${index}`, sources: [link.source], targets: [link.target],
      })),
    });
    const sections = (result.edges?.[0] as typeof result.edges[number] & {
      sections?: { bendPoints?: unknown[] }[];
    })?.sections;
    expect(sections?.length).toBeGreaterThan(0);
  });
});
