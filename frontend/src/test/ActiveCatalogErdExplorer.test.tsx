import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActiveCatalogErdExplorer } from "../components/ActiveCatalogErdExplorer";
import { listActiveCatalogs } from "../api/catalog";
import { loadActiveCatalogErd } from "../api/catalogErd";
import { activeSource, secondSource, tablesResponse } from "./mocks";
import type { CatalogErdSnapshot } from "../api/catalogErd";

vi.mock("../api/catalog", () => ({ listActiveCatalogs: vi.fn() }));
vi.mock("../api/catalogErd", () => ({ loadActiveCatalogErd: vi.fn() }));
vi.mock("../components/CatalogErdCanvas", () => ({
  CatalogErdCanvas: ({ tables, onTableSelect }: {
    tables: { id: string; name: string }[];
    onTableSelect: (id: string) => void;
  }) => <div data-testid="mock-erd-canvas">
    {tables.map((table) => <button key={table.id} type="button"
      onClick={() => onTableSelect(table.id)}>{table.name}</button>)}
  </div>,
}));

const data: CatalogErdSnapshot = {
  active: activeSource,
  tables: [tablesResponse.items[0], {
    schema_name: "DEMIS_OWNER", name: "TB_ENC_HIST", comment: "진료",
    table_type: "BASE TABLE", category_ids: ["clinical"],
  }],
  relations: [{
    name: "FK_ADM_ENC", schema_name: "DEMIS_OWNER", table_name: "TB_ADM_HIST",
    referenced_schema_name: "DEMIS_OWNER", referenced_table_name: "TB_ENC_HIST",
    columns: [{ column: "ENC_ID", referenced_column: "ENC_ID" }],
  }],
  categories: [{ id: "clinical", name: "진료", description: null, assignments: [] }],
  totalTables: 2, totalRelations: 1, totalCategories: 1, truncated: false,
};

afterEach(() => {
  sessionStorage.clear();
  vi.resetAllMocks();
});

describe("ERD Explorer UI", () => {
  it("uses active Catalog metadata for full, focus, category and relation views", async () => {
    const user = userEvent.setup();
    vi.mocked(listActiveCatalogs).mockResolvedValue([activeSource]);
    vi.mocked(loadActiveCatalogErd).mockResolvedValue(data);
    render(<ActiveCatalogErdExplorer />);

    expect(await screen.findByTestId("mock-erd-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("active-catalog-status")).toBeInTheDocument();
    expect(screen.getByText("FK 관계선", { exact: false })).not.toBeNull();
    expect(screen.getAllByText("TB_ADM_HIST").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "TB_ADM_HIST" }));
    expect(screen.getByRole("button", { name: "이 테이블 중심 보기" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "이 테이블 중심 보기" }));
    expect(screen.getByLabelText("ERD 보기 방식")).toHaveValue("neighborhood");
    expect(screen.getByLabelText("ERD 관계 단계")).toHaveValue("1");
    expect(screen.getByText(/FK_ADM_ENC/)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("ERD 보기 방식"), "category");
    await user.selectOptions(screen.getByLabelText("ERD Category"), "clinical");
    expect(screen.getByRole("button", { name: "TB_ENC_HIST" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "TB_ADM_HIST" })).not.toBeInTheDocument();

    await user.type(screen.getByLabelText("ERD 테이블 검색"), "존재하지않음");
    expect(screen.getByText("조건에 맞는 Table이 없습니다.")).toBeInTheDocument();
    expect(loadActiveCatalogErd).toHaveBeenCalledTimes(1);
  });

  it("discards slow responses from a source that is no longer selected", async () => {
    const user = userEvent.setup();
    vi.mocked(listActiveCatalogs).mockResolvedValue([activeSource, secondSource]);
    let resolveOld!: (value: CatalogErdSnapshot) => void;
    vi.mocked(loadActiveCatalogErd).mockImplementation((source) => source === activeSource.source_name
      ? new Promise((resolve) => { resolveOld = resolve; })
      : Promise.resolve({ ...data, active: secondSource, totalTables: 0, tables: [] }));
    render(<ActiveCatalogErdExplorer />);
    const selector = await screen.findByLabelText("Active Catalog source");
    await waitFor(() => expect(loadActiveCatalogErd).toHaveBeenCalledWith(activeSource.source_name));
    await user.selectOptions(selector, secondSource.source_name);
    expect(await screen.findByText("활성 Catalog에 테이블이 없습니다.")).toBeInTheDocument();

    resolveOld(data);
    await waitFor(() => expect(screen.queryByTestId("mock-erd-canvas")).not.toBeInTheDocument());
    expect(screen.queryByText("TB_ADM_HIST")).not.toBeInTheDocument();
  });

  it("hides loaded metadata as soon as the user switches source", async () => {
    const user = userEvent.setup();
    vi.mocked(listActiveCatalogs).mockResolvedValue([activeSource, secondSource]);
    let resolveNext!: (value: CatalogErdSnapshot) => void;
    vi.mocked(loadActiveCatalogErd).mockImplementation((source) => source === activeSource.source_name
      ? Promise.resolve(data)
      : new Promise((resolve) => { resolveNext = resolve; }));
    render(<ActiveCatalogErdExplorer />);
    expect(await screen.findByTestId("mock-erd-canvas")).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Active Catalog source"), secondSource.source_name);
    expect(screen.queryByTestId("mock-erd-canvas")).not.toBeInTheDocument();
    expect(screen.queryByText("TB_ADM_HIST")).not.toBeInTheDocument();
    resolveNext({ ...data, active: secondSource, tables: [], totalTables: 0 });
    expect(await screen.findByText("활성 Catalog에 테이블이 없습니다.")).toBeInTheDocument();
  });
});
