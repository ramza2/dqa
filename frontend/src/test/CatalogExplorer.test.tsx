import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CatalogExplorer } from "../components/CatalogExplorer";
import {
  activeSource,
  defaultCatalogHandlers,
  installFetchMock,
  jsonResponse,
  secondSource,
  tablesResponse,
} from "./mocks";

afterEach(() => {
  vi.useRealTimers();
});

describe("CatalogExplorer", () => {
  it("auto-selects a single active source and shows revision/fingerprint", async () => {
    const restore = installFetchMock(defaultCatalogHandlers());
    render(<CatalogExplorer />);

    expect(await screen.findByTestId("active-catalog-status")).toBeInTheDocument();
    expect(screen.getAllByText("oracle_demis_mock").length).toBeGreaterThan(0);
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(screen.getByTitle(activeSource.schema_fingerprint)).toBeInTheDocument();
    restore();
  });

  it("renders table list and supports q search", async () => {
    const user = userEvent.setup();
    let seenQ: string | null = null;
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => {
      if (url.pathname.endsWith("/tables") && !url.pathname.includes("/tables/")) {
        seenQ = url.searchParams.get("q");
        return jsonResponse(tablesResponse);
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    render(<CatalogExplorer />);

    expect(await screen.findByText("TB_ADM_HIST")).toBeInTheDocument();
    expect(screen.getByText("환자 입원 이력")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Search tables"), "adm");
    await waitFor(() => {
      expect(seenQ).toBe("adm");
    });
    restore();
  });

  it("loads table detail, columns, relations, indexes, and category empty state", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(defaultCatalogHandlers());
    render(<CatalogExplorer />);

    await screen.findByText("TB_ADM_HIST");
    await user.click(screen.getByRole("button", { name: /TB_ADM_HIST/i }));

    expect(await screen.findByText("Overview")).toBeInTheDocument();
    expect(screen.getAllByText("BASE TABLE").length).toBeGreaterThan(0);
    expect(screen.getAllByText("환자 입원 이력").length).toBeGreaterThan(0);

    expect(screen.getByText("WARD_CD")).toBeInTheDocument();
    expect(screen.getByText("입원 병동 코드")).toBeInTheDocument();
    expect(screen.getByText("PK")).toBeInTheDocument();
    expect(screen.getAllByText("Unique").length).toBeGreaterThan(0);
    expect(screen.getByText("YES")).toBeInTheDocument();
    expect(screen.getByText("NO")).toBeInTheDocument();

    expect(screen.getByText("FK_ADM_ENC")).toBeInTheDocument();
    expect(screen.getByText("OUT")).toBeInTheDocument();
    expect(screen.getByText("IN")).toBeInTheDocument();
    expect(screen.getByText("ENC_ID → ENC_ID")).toBeInTheDocument();

    expect(screen.getByText("IX_ADM_ENC")).toBeInTheDocument();
    expect(screen.getByText("NORMAL")).toBeInTheDocument();

    const categories = screen.getByLabelText("Categories");
    expect(within(categories).getByText(/No categories in this Catalog/i)).toBeInTheDocument();
    restore();
  });

  it("shows API error state with backend code", async () => {
    const restore = installFetchMock([
      () =>
        jsonResponse(
          {
            detail: {
              code: "CATALOG_ACTIVE_REVISION_NOT_FOUND",
              message: "active catalog revision not found for source",
            },
          },
          404,
        ),
    ]);
    render(<CatalogExplorer />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("CATALOG_ACTIVE_REVISION_NOT_FOUND")).toBeInTheDocument();
    expect(screen.getByText(/Catalog data could not be loaded/i)).toBeInTheDocument();
    restore();
  });

  it("shows empty state when no active Catalog exists", async () => {
    const restore = installFetchMock(defaultCatalogHandlers({ actives: [] }));
    render(<CatalogExplorer />);
    expect(await screen.findByText("No active Catalog")).toBeInTheDocument();
    restore();
  });

  it("clears selected table when source changes", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      defaultCatalogHandlers({ actives: [activeSource, secondSource] }),
    );
    render(<CatalogExplorer />);

    await screen.findByLabelText("Active Catalog source");
    await user.click(await screen.findByRole("button", { name: /TB_ADM_HIST/i }));
    expect(await screen.findByText("Overview")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Active Catalog source"), "oracle_demis_other");
    await waitFor(() => {
      expect(screen.queryByText("Overview")).not.toBeInTheDocument();
    });
    expect(screen.getByText(/Select a table to inspect metadata/i)).toBeInTheDocument();
    restore();
  });

  it("warns when query revision/fingerprint mismatches active header", async () => {
    const restore = installFetchMock(defaultCatalogHandlers({ staleTables: true }));
    render(<CatalogExplorer />);
    expect(
      await screen.findByText(/Catalog revision changed\. Refreshing metadata/i),
    ).toBeInTheDocument();
    restore();
  });
});
