import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { FocusedErdPanel } from "../components/FocusedErdPanel";
import { CatalogExplorer } from "../components/CatalogExplorer";
import { buildFocusedErd } from "../utils/focusedErd";
import type { DirectedRelation } from "../types/catalog";
import { activeSource, defaultCatalogHandlers, installFetchMock, tablesResponse } from "./mocks";

const outgoing: DirectedRelation = {
  direction: "OUT",
  key: "o",
  name: "FK_COMPOSITE",
  sourceSchema: "DEMIS_OWNER",
  sourceTable: "TB_ADM_HIST",
  targetSchema: "REFERENCE_OWNER",
  targetTable: "TB_REFERENCE",
  columns: [
    { column: "VISIT_ID", referenced_column: "ID" },
    { column: "SITE_ID", referenced_column: "SITE" },
  ],
};
const incoming: DirectedRelation = {
  ...outgoing,
  direction: "IN",
  key: "i",
  name: "FK_CHILD_PARENT",
  sourceSchema: "DEMIS_OWNER",
  sourceTable: "TB_CHILD",
  targetSchema: "DEMIS_OWNER",
  targetTable: "TB_ADM_HIST",
  columns: [{ column: "PARENT_ID", referenced_column: "ADM_ID" }],
};

describe("M2-2A bounded active Catalog ERD", () => {
  it("keeps FK directions, composite order and external reference warning", () => {
    const graph = buildFocusedErd("DEMIS_OWNER", "TB_ADM_HIST",
      [outgoing, incoming, outgoing]);
    expect(graph.total).toBe(2);
    expect(graph.inbound).toHaveLength(1);
    expect(graph.outbound).toHaveLength(1);
    expect(graph.outbound[0].outsideSchema).toBe(true);
    expect(graph.outbound[0].columns.map(c => c.column)).toEqual(["VISIT_ID", "SITE_ID"]);

    render(<FocusedErdPanel detail={tablesResponse.items[0]}
      relations={[outgoing, incoming]} source={activeSource.source_name}
      revision={activeSource.revision_id} />);
    const region = screen.getByRole("region", { name: "테이블 관계 ERD" });
    expect(within(region).getByText("DEMIS_OWNER.TB_ADM_HIST")).toBeInTheDocument();
    expect(within(region).getByText("VISIT_ID → ID, SITE_ID → SITE")).toBeInTheDocument();
    expect(within(region).getByText("외부 스키마 참조 (권한 미확인)")).toBeInTheDocument();
  });

  it("rejects ambiguous/schema-collision relations and caps rendered edges", () => {
    const crossSchemaSameName = { ...incoming, targetSchema: "OTHER_OWNER" };
    const missingSchema = { ...outgoing, targetSchema: null };
    const graph = buildFocusedErd("DEMIS_OWNER", "TB_ADM_HIST",
      [crossSchemaSameName, missingSchema, outgoing, incoming]);
    expect(graph.total).toBe(2);
    expect(graph.unknown).toBe(2);
    const capped = buildFocusedErd("DEMIS_OWNER", "TB_ADM_HIST",
      [outgoing, incoming], 1);
    expect(capped.total).toBe(2);
    expect(capped.hidden).toBe(1);
  });

  it("exposes ERD within existing Explorer without extra API or inactive revisions", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(defaultCatalogHandlers());
    try {
      render(<CatalogExplorer />);
      await user.click(await screen.findByRole("button", { name: /TB_ADM_HIST/i }));
      expect(await screen.findByText("Overview")).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "관계 ERD" }));
      const region = await screen.findByRole("region", { name: "테이블 관계 ERD" });
      expect(within(region).getByText("DEMIS_OWNER.TB_ADM_HIST")).toBeInTheDocument();
      expect(within(region).getByText(/FK_ADM_ENC/)).toBeInTheDocument();
      expect(within(region).getByText(/FK_OTHER_TO_ADM/)).toBeInTheDocument();
      expect(within(region).getByText(/Revision: 1/)).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "상세정보" }));
      expect(await screen.findByText("Overview")).toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "테이블 관계 ERD" })).not.toBeInTheDocument();
    } finally {
      restore();
    }
  });

  it("never renders graph after source change until new detail accepted", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(defaultCatalogHandlers({
      actives: [activeSource, { ...activeSource, source_name: "other_source", revision_id: 2 }],
    }));
    try {
      render(<CatalogExplorer />);
      await user.click(await screen.findByRole("button", { name: /TB_ADM_HIST/i }));
      await screen.findByText("Overview");
      await user.click(screen.getByRole("button", { name: "관계 ERD" }));
      expect(await screen.findByRole("region", { name: "테이블 관계 ERD" })).toBeInTheDocument();
      await user.selectOptions(screen.getByLabelText("Active Catalog source"), "other_source");
      await waitFor(() => {
        expect(screen.queryByRole("region", { name: "테이블 관계 ERD" })).not.toBeInTheDocument();
      });
    } finally {
      restore();
    }
  });
});
