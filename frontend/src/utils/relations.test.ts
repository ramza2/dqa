import { describe, expect, it } from "vitest";
import { mergeDirectedRelations } from "../utils/relations";
import type { CatalogRelationItem } from "../types/catalog";

describe("mergeDirectedRelations", () => {
  it("keeps outgoing and schema-filtered incoming relations", () => {
    const outgoing: CatalogRelationItem[] = [
      {
        name: "FK_OUT",
        schema_name: "DEMIS_OWNER",
        table_name: "TB_ADM_HIST",
        referenced_schema_name: "DEMIS_OWNER",
        referenced_table_name: "TB_ENC_HIST",
        columns: [{ column: "ENC_ID", referenced_column: "ENC_ID" }],
      },
    ];
    const incoming: CatalogRelationItem[] = [
      {
        name: "FK_IN",
        schema_name: "DEMIS_OWNER",
        table_name: "TB_OTHER",
        referenced_schema_name: "DEMIS_OWNER",
        referenced_table_name: "TB_ADM_HIST",
        columns: [{ column: "ADM_ID", referenced_column: "ADM_ID" }],
      },
      {
        name: "FK_OTHER_SCHEMA",
        schema_name: "OTHER",
        table_name: "TB_X",
        referenced_schema_name: "OTHER",
        referenced_table_name: "TB_ADM_HIST",
        columns: [{ column: "ID", referenced_column: "ADM_ID" }],
      },
    ];

    const merged = mergeDirectedRelations(outgoing, incoming, "DEMIS_OWNER");
    expect(merged).toHaveLength(2);
    expect(merged.map((item) => item.direction).sort()).toEqual(["IN", "OUT"]);
    expect(merged.find((item) => item.name === "FK_OTHER_SCHEMA")).toBeUndefined();
  });
});
