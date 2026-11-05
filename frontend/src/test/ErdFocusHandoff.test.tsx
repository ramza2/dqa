import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataDiscoveryPortal } from "../components/DataDiscoveryPortal";
import { ActiveCatalogErdExplorer } from "../components/ActiveCatalogErdExplorer";
import { CatalogSourceProvider } from "../components/CatalogSourceContext";
import { ErdFocusProvider } from "../components/ErdFocusContext";
import { loadActiveCatalogErd } from "../api/catalogErd";
import { tableIdentity } from "../utils/catalogErd";
import {
  activeSource,
  defaultCatalogHandlers,
  installFetchMock,
  secondSource,
  tablesResponse,
} from "./mocks";
import type { CatalogErdSnapshot } from "../api/catalogErd";

vi.mock("../api/catalogErd", () => ({ loadActiveCatalogErd: vi.fn() }));
vi.mock("../components/CatalogErdCanvas", () => ({
  CatalogErdCanvas: ({
    tables,
    selectedTable,
    selectedLink,
    onTableSelect,
    onLinkSelect,
    links,
  }: {
    tables: { id: string; name: string }[];
    selectedTable: string;
    selectedLink: string;
    onTableSelect: (id: string) => void;
    onLinkSelect: (id: string) => void;
    links: { id: string; name: string | null; mapping: { source: string; target: string }[] }[];
  }) => (
    <div data-testid="mock-erd-canvas">
      <div data-testid="mock-selected-table">{selectedTable}</div>
      <div data-testid="mock-selected-link">{selectedLink}</div>
      {tables.map((table) => (
        <button key={table.id} type="button" onClick={() => onTableSelect(table.id)}>
          {table.name}
        </button>
      ))}
      {links.map((link) => (
        <button key={link.id} type="button" onClick={() => onLinkSelect(link.id)}>
          link:{link.name ?? "FK"}
        </button>
      ))}
    </div>
  ),
}));

const erdData: CatalogErdSnapshot = {
  active: activeSource,
  tables: [
    tablesResponse.items[0],
    {
      schema_name: "DEMIS_OWNER",
      name: "TB_ENC_HIST",
      comment: "진료",
      table_type: "BASE TABLE",
      category_ids: ["clinical"],
    },
    {
      schema_name: "DEMIS_OWNER",
      name: "TB_LAB",
      comment: "검사",
      table_type: "BASE TABLE",
      category_ids: [],
    },
  ],
  relations: [
    {
      name: "FK_ADM_ENC",
      schema_name: "DEMIS_OWNER",
      table_name: "TB_ADM_HIST",
      referenced_schema_name: "DEMIS_OWNER",
      referenced_table_name: "TB_ENC_HIST",
      columns: [
        { column: "ENC_ID", referenced_column: "ENC_ID" },
        { column: "SITE_CD", referenced_column: "SITE_CD" },
      ],
    },
    {
      name: "FK_LAB_ENC",
      schema_name: "DEMIS_OWNER",
      table_name: "TB_LAB",
      referenced_schema_name: "DEMIS_OWNER",
      referenced_table_name: "TB_ENC_HIST",
      columns: [{ column: "ENC_ID", referenced_column: "ENC_ID" }],
    },
  ],
  categories: [{ id: "clinical", name: "진료", description: null, assignments: [] }],
  totalTables: 3,
  totalRelations: 2,
  totalCategories: 1,
  truncated: false,
};

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("M5-UX4A ERD neighborhood focus and handoff", () => {
  it("opens ERD Explorer focused on the Table Explorer selection", async () => {
    const user = userEvent.setup();
    vi.mocked(loadActiveCatalogErd).mockResolvedValue(erdData);
    const restore = installFetchMock(defaultCatalogHandlers());
    render(<DataDiscoveryPortal />);

    await user.click(screen.getByTestId("dd-tab-explorer"));
    await user.click(await screen.findByRole("button", { name: /TB_ADM_HIST/i }));
    await screen.findByText("Overview");
    await user.click(screen.getByRole("button", { name: "관계 ERD" }));
    await user.click(await screen.findByTestId("open-full-erd-explorer"));

    expect(await screen.findByTestId("active-catalog-erd-explorer")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText("ERD 보기 방식")).toHaveValue("neighborhood");
    });
    expect(screen.getByLabelText("ERD 중심 테이블")).toHaveValue(
      tableIdentity("DEMIS_OWNER", "TB_ADM_HIST"),
    );
    expect(screen.getByTestId("mock-selected-table")).toHaveTextContent(
      tableIdentity("DEMIS_OWNER", "TB_ADM_HIST"),
    );
    restore();
  });

  it("shows structured FK column mapping when a relation is selected", async () => {
    const user = userEvent.setup();
    vi.mocked(loadActiveCatalogErd).mockResolvedValue(erdData);
    const restore = installFetchMock(defaultCatalogHandlers());
    render(
      <CatalogSourceProvider>
        <ErdFocusProvider>
          <ActiveCatalogErdExplorer />
        </ErdFocusProvider>
      </CatalogSourceProvider>,
    );

    expect(await screen.findByTestId("mock-erd-canvas")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "link:FK_ADM_ENC" }));
    const detail = await screen.findByTestId("erd-relation-detail");
    expect(within(detail).getByText("FK_ADM_ENC")).toBeInTheDocument();
    expect(within(detail).getByRole("columnheader", { name: "Source column" })).toBeInTheDocument();
    expect(within(detail).getByRole("columnheader", { name: "Referenced column" })).toBeInTheDocument();
    expect(within(detail).getAllByText("ENC_ID").length).toBeGreaterThan(0);
    expect(within(detail).getAllByText("SITE_CD").length).toBeGreaterThan(0);
    restore();
  });

  it("exposes 1–3 hop neighborhood options and clears graph on source change", async () => {
    const user = userEvent.setup();
    vi.mocked(loadActiveCatalogErd).mockImplementation(async (source) => {
      if (source === secondSource.source_name) {
        return { ...erdData, active: secondSource, tables: [], totalTables: 0 };
      }
      return erdData;
    });
    const restore = installFetchMock(
      defaultCatalogHandlers({ actives: [activeSource, secondSource] }),
    );
    render(
      <CatalogSourceProvider>
        <ActiveCatalogErdExplorer />
      </CatalogSourceProvider>,
    );

    expect(await screen.findByTestId("mock-erd-canvas")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("ERD 보기 방식"), "neighborhood");
    await user.selectOptions(
      screen.getByLabelText("ERD 중심 테이블"),
      tableIdentity("DEMIS_OWNER", "TB_ADM_HIST"),
    );
    const hopSelect = screen.getByLabelText("ERD 관계 단계");
    expect(within(hopSelect).getByRole("option", { name: "3단계 FK" })).toBeInTheDocument();
    await user.selectOptions(hopSelect, "3");
    expect(hopSelect).toHaveValue("3");

    await user.selectOptions(
      screen.getByLabelText("Active Catalog source"),
      secondSource.source_name,
    );
    expect(await screen.findByText("활성 Catalog에 테이블이 없습니다.")).toBeInTheDocument();
    expect(screen.queryByTestId("mock-erd-canvas")).not.toBeInTheDocument();
    restore();
  });
});
