import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CatalogExplorer } from "../components/CatalogExplorer";
import type { CatalogActiveSummary, CatalogCategoryListResponse } from "../types/catalog";
import {
  activeSource,
  columnsResponse,
  defaultCatalogHandlers,
  emptyCategories,
  indexesResponse,
  incomingRelations,
  installFetchMock,
  jsonResponse,
  outgoingRelations,
  secondSource,
  tableDetailResponse,
  tablesResponse,
} from "./mocks";

afterEach(() => {
  vi.useRealTimers();
});

const activeRev2: CatalogActiveSummary = {
  ...activeSource,
  revision_id: 2,
  schema_fingerprint: "fp-revision-2-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
};

const staleCategories: CatalogCategoryListResponse = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint: "fp-revision-1-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  total: 1,
  limit: 500,
  offset: 0,
  items: [
    {
      id: "stale_cat",
      name: "Stale Category Name",
      description: "should not render",
      assignments: [],
    },
  ],
};

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

  it("rejects stale category responses without committing old rows", async () => {
    const handlers = defaultCatalogHandlers({ actives: [activeRev2] });
    handlers.unshift((url) => {
      if (url.pathname.endsWith("/categories")) {
        return jsonResponse(staleCategories);
      }
      if (url.pathname.endsWith("/tables") && !url.pathname.includes("/tables/")) {
        return jsonResponse({
          ...tablesResponse,
          revision_id: 2,
          schema_fingerprint: activeRev2.schema_fingerprint,
        });
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    render(<CatalogExplorer />);

    expect(
      await screen.findByText(/Catalog revision changed\. Refreshing metadata/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Stale Category Name")).not.toBeInTheDocument();
    restore();
  });

  it("bounds active refresh when categories stay stale on the same revision", async () => {
    let activeFetchCount = 0;
    const restore = installFetchMock([
      (url) => {
        if (url.pathname === "/api/v1/catalog/active") {
          return jsonResponse([activeRev2]);
        }
        return null;
      },
      (url) => {
        const match = url.pathname.match(/^\/api\/v1\/catalog\/active\/([^/]+)$/);
        if (!match) {
          return null;
        }
        activeFetchCount += 1;
        return jsonResponse(activeRev2);
      },
      (url) => {
        if (!(url.pathname.endsWith("/tables") && !url.pathname.includes("/tables/"))) {
          return null;
        }
        return jsonResponse({
          ...tablesResponse,
          revision_id: 2,
          schema_fingerprint: activeRev2.schema_fingerprint,
        });
      },
      (url) => {
        if (!url.pathname.endsWith("/categories")) {
          return null;
        }
        return jsonResponse(staleCategories);
      },
    ]);

    render(<CatalogExplorer />);

    expect(
      await screen.findByText(/Catalog revision changed\. Refreshing metadata/i),
    ).toBeInTheDocument();
    expect(await screen.findByText("TB_ADM_HIST")).toBeInTheDocument();
    expect(screen.queryByText("Stale Category Name")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(activeFetchCount).toBeGreaterThanOrEqual(2);
    });

    const settledCount = activeFetchCount;
    expect(settledCount).toBeLessThanOrEqual(3);

    await new Promise((resolve) => {
      setTimeout(resolve, 250);
    });

    expect(activeFetchCount).toBe(settledCount);
    expect(
      screen.getByText(/Catalog revision changed\. Refreshing metadata/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Stale Category Name")).not.toBeInTheDocument();
    restore();
  });

  it("does not render mixed detail batch from divergent revisions", async () => {
    const user = userEvent.setup();
    const handlers = defaultCatalogHandlers({ actives: [activeRev2] });
    handlers.unshift((url) => {
      if (url.pathname.endsWith("/tables") && !url.pathname.includes("/tables/")) {
        return jsonResponse({
          ...tablesResponse,
          revision_id: 2,
          schema_fingerprint: activeRev2.schema_fingerprint,
        });
      }
      if (url.pathname.endsWith("/categories")) {
        return jsonResponse({
          ...emptyCategories,
          revision_id: 2,
          schema_fingerprint: activeRev2.schema_fingerprint,
        });
      }
      if (url.pathname.includes("/tables/DEMIS_OWNER/TB_ADM_HIST")) {
        return jsonResponse({
          ...tableDetailResponse,
          revision_id: 2,
          schema_fingerprint: activeRev2.schema_fingerprint,
        });
      }
      if (url.pathname.endsWith("/columns")) {
        return jsonResponse({
          ...columnsResponse,
          revision_id: 1,
          schema_fingerprint: "fp-old",
        });
      }
      if (url.pathname.endsWith("/relations")) {
        const base = url.searchParams.get("referenced_table_name")
          ? incomingRelations
          : outgoingRelations;
        return jsonResponse({
          ...base,
          revision_id: 2,
          schema_fingerprint: activeRev2.schema_fingerprint,
        });
      }
      if (url.pathname.endsWith("/indexes")) {
        return jsonResponse({
          ...indexesResponse,
          revision_id: 2,
          schema_fingerprint: activeRev2.schema_fingerprint,
        });
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    render(<CatalogExplorer />);

    await screen.findByText("TB_ADM_HIST");
    await user.click(screen.getByRole("button", { name: /TB_ADM_HIST/i }));

    expect(
      await screen.findByText(/Catalog revision changed\. Refreshing metadata/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Overview")).not.toBeInTheDocument();
    expect(screen.queryByText("WARD_CD")).not.toBeInTheDocument();
    restore();
  });

  it("converges header/tables/categories/detail after mismatch refresh", async () => {
    const user = userEvent.setup();
    let activeFetches = 0;
    const freshMeta = {
      revision_id: 2,
      schema_fingerprint: activeRev2.schema_fingerprint,
    };

    const restore = installFetchMock([
      (url) => {
        if (url.pathname === "/api/v1/catalog/active") {
          return jsonResponse([activeRev2]);
        }
        return null;
      },
      (url) => {
        const match = url.pathname.match(/^\/api\/v1\/catalog\/active\/([^/]+)$/);
        if (!match) {
          return null;
        }
        activeFetches += 1;
        // Delay the guarded refresh response so the stale warning is observable
        // before tables/categories converge on the fresh revision.
        if (activeFetches > 1) {
          return new Promise((resolve) => {
            setTimeout(() => {
              resolve(jsonResponse(activeRev2));
            }, 40);
          });
        }
        return jsonResponse(activeRev2);
      },
      (url) => {
        if (!(url.pathname.endsWith("/tables") && !url.pathname.includes("/tables/"))) {
          return null;
        }
        if (activeFetches <= 1) {
          return jsonResponse({
            ...tablesResponse,
            revision_id: 1,
            schema_fingerprint: "fp-old",
          });
        }
        return jsonResponse({ ...tablesResponse, ...freshMeta });
      },
      (url) => {
        if (!url.pathname.endsWith("/categories")) {
          return null;
        }
        if (activeFetches <= 1) {
          return jsonResponse(staleCategories);
        }
        return jsonResponse({ ...emptyCategories, ...freshMeta });
      },
      (url) => {
        if (!url.pathname.includes("/tables/DEMIS_OWNER/TB_ADM_HIST")) {
          return null;
        }
        return jsonResponse({ ...tableDetailResponse, ...freshMeta });
      },
      (url) => {
        if (!url.pathname.endsWith("/columns")) {
          return null;
        }
        return jsonResponse({ ...columnsResponse, ...freshMeta });
      },
      (url) => {
        if (!url.pathname.endsWith("/relations")) {
          return null;
        }
        const base = url.searchParams.get("referenced_table_name")
          ? incomingRelations
          : outgoingRelations;
        return jsonResponse({ ...base, ...freshMeta });
      },
      (url) => {
        if (!url.pathname.endsWith("/indexes")) {
          return null;
        }
        return jsonResponse({ ...indexesResponse, ...freshMeta });
      },
    ]);

    render(<CatalogExplorer />);

    expect(
      await screen.findByText(/Catalog revision changed\. Refreshing metadata/i),
    ).toBeInTheDocument();

    expect(await screen.findByText("TB_ADM_HIST")).toBeInTheDocument();
    expect(screen.getByTitle(activeRev2.schema_fingerprint)).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.queryByText(/Catalog revision changed\. Refreshing metadata/i),
      ).not.toBeInTheDocument();
    });

    const categories = screen.getByLabelText("Categories");
    expect(within(categories).getByText(/No categories in this Catalog/i)).toBeInTheDocument();
    expect(screen.queryByText("Stale Category Name")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /TB_ADM_HIST/i }));
    expect(await screen.findByText("Overview")).toBeInTheDocument();
    expect(screen.getByText("WARD_CD")).toBeInTheDocument();
    restore();
  });

  it("ignores late responses from a previous source after switch", async () => {
    const user = userEvent.setup();
    let resolveOldTables: ((value: Response) => void) | undefined;
    const oldTablesPromise = new Promise<Response>((resolve) => {
      resolveOldTables = resolve;
    });

    const restore = installFetchMock([
      (url) => {
        if (url.pathname === "/api/v1/catalog/active") {
          return jsonResponse([activeSource, secondSource]);
        }
        return null;
      },
      (url) => {
        const match = url.pathname.match(/^\/api\/v1\/catalog\/active\/([^/]+)$/);
        if (!match) {
          return null;
        }
        const source = decodeURIComponent(match[1]);
        if (source === secondSource.source_name) {
          return jsonResponse(secondSource);
        }
        return jsonResponse(activeSource);
      },
      (url) => {
        if (!(url.pathname.endsWith("/tables") && !url.pathname.includes("/tables/"))) {
          return null;
        }
        if (url.pathname.includes(secondSource.source_name)) {
          return jsonResponse({
            ...tablesResponse,
            source_name: secondSource.source_name,
            revision_id: secondSource.revision_id,
            schema_fingerprint: secondSource.schema_fingerprint,
            items: [
              {
                schema_name: "DEMIS_OTHER",
                name: "TB_B_ONLY",
                comment: "b only",
                table_type: "TABLE",
                category_ids: [],
              },
            ],
          });
        }
        return oldTablesPromise;
      },
      (url) => {
        if (!url.pathname.endsWith("/categories")) {
          return null;
        }
        if (url.pathname.includes(secondSource.source_name)) {
          return jsonResponse({
            ...emptyCategories,
            source_name: secondSource.source_name,
            revision_id: secondSource.revision_id,
            schema_fingerprint: secondSource.schema_fingerprint,
          });
        }
        return jsonResponse(emptyCategories);
      },
    ]);

    render(<CatalogExplorer />);
    await screen.findByLabelText("Active Catalog source");

    await user.selectOptions(
      screen.getByLabelText("Active Catalog source"),
      secondSource.source_name,
    );

    expect(await screen.findByText("TB_B_ONLY")).toBeInTheDocument();

    resolveOldTables!(
      jsonResponse({
        ...tablesResponse,
        items: [
          {
            schema_name: "DEMIS_OWNER",
            name: "TB_SHOULD_NOT_APPEAR",
            comment: "late",
            table_type: "TABLE",
            category_ids: [],
          },
        ],
      }),
    );

    await waitFor(() => {
      expect(screen.queryByText("TB_SHOULD_NOT_APPEAR")).not.toBeInTheDocument();
    });
    expect(screen.getByText("TB_B_ONLY")).toBeInTheDocument();
    restore();
  });
});
