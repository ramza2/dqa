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
  sessionStorage.clear();
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

    const status = await screen.findByTestId("active-catalog-status");
    expect(screen.getAllByText("oracle_demis_mock").length).toBeGreaterThan(0);
    expect(within(status).getByText("1")).toBeInTheDocument();
    expect(within(status).getByText("READY")).toBeInTheDocument();
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

    expect(await screen.findByText("테이블 개요")).toBeInTheDocument();
    expect(screen.getAllByText("BASE TABLE").length).toBeGreaterThan(0);
    expect(screen.getAllByText("환자 입원 이력").length).toBeGreaterThan(0);

    expect(screen.getByText("WARD_CD")).toBeInTheDocument();
    expect(screen.getByText("입원 병동 코드")).toBeInTheDocument();
    expect(screen.getByText("PK")).toBeInTheDocument();
    expect(screen.getAllByText("Unique").length).toBeGreaterThan(0);
    expect(screen.getByText("YES")).toBeInTheDocument();
    expect(screen.getByText("NO")).toBeInTheDocument();

    expect(screen.getByText("참조하는 FK")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: /관계 2/i }));
    expect(screen.getByText("FK_ADM_ENC")).toBeInTheDocument();
    expect(screen.getByText("참조하는 FK (1)")).toBeInTheDocument();
    expect(screen.getByText("참조받는 FK (1)")).toBeInTheDocument();
    expect(screen.getByText("ENC_ID → ENC_ID")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /인덱스 1/i }));
    expect(screen.getByText("IX_ADM_ENC")).toBeInTheDocument();
    expect(screen.getByText("NORMAL")).toBeInTheDocument();

    const categories = screen.getByLabelText("Categories");
    expect(within(categories).getByText(/등록된 분류 정보가 없습니다/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Category 필터")).toBeDisabled();
    expect(screen.getByTestId("catalog-category-empty-guidance")).toHaveTextContent("테이블·컬럼·관계 탐색은 정상적으로");
    restore();
  });

  it("filters active tables by schema and category without changing server source", async () => {
    const user = userEvent.setup();
    const seenFilters: Array<{ schema: string | null; category: string | null }> = [];
    const category = {
      id: "clinical",
      name: "진료",
      description: null,
      assignments: [{
        schema_name: "DEMIS_OWNER",
        table_name: "TB_ADM_HIST",
        provenance: "reviewed",
        is_primary: true,
        confidence: 0.9,
        note: "reviewed assignment",
      }],
    };
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => {
      if (url.pathname.endsWith("/tables")) {
        seenFilters.push({
          schema: url.searchParams.get("schema_name"),
          category: url.searchParams.get("category"),
        });
        const all = [
          { ...tablesResponse.items[0], category_ids: ["clinical"] },
          { schema_name: "OTHER", name: "TB_DEVICE", comment: "장비", table_type: "BASE TABLE", category_ids: [] },
        ];
        const schema = url.searchParams.get("schema_name");
        const categoryKey = url.searchParams.get("category");
        const items = all.filter((table) =>
          (!schema || table.schema_name === schema) &&
          (!categoryKey || table.category_ids.includes(categoryKey)),
        );
        return jsonResponse({
          ...tablesResponse,
          total: items.length,
          items,
        });
      }
      if (url.pathname.endsWith("/categories")) {
        return jsonResponse({ ...emptyCategories, total: 1, items: [category] });
      }
      return null;
    });
    const restore = installFetchMock(handlers);
    render(<CatalogExplorer />);

    expect(await screen.findByRole("button", { name: /TB_DEVICE/i })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Category 필터"), "clinical");
    await waitFor(() => expect(seenFilters.some((item) => item.category === "clinical")).toBe(true));
    expect(screen.queryByRole("button", { name: /TB_DEVICE/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /TB_ADM_HIST/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /TB_ADM_HIST/i }));
    await screen.findByText("테이블 개요");
    await user.click(screen.getByRole("tab", { name: /분류 1/i }));
    expect(screen.getByText("reviewed assignment")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Schema 필터"), "OTHER");
    expect(await screen.findByText("검색 조건에 맞는 테이블이 없습니다.")).toBeInTheDocument();
    expect(seenFilters.some((item) => item.category === "clinical" && item.schema === "OTHER")).toBe(true);
    expect(screen.queryByText("reviewed assignment")).not.toBeInTheDocument();
    restore();
  });

  it("warns when the server returns only a bounded first page", async () => {
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => url.pathname.endsWith("/tables")
      ? jsonResponse({ ...tablesResponse, total: 1001 }) : null);
    const restore = installFetchMock(handlers);
    render(<CatalogExplorer />);
    expect(await screen.findByText(/검색 결과 1001건 중 서버가 반환한 1건만 탐색합니다/)).toBeInTheDocument();
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
    expect(screen.getByText(/Catalog 데이터를 불러오지 못했습니다/i)).toBeInTheDocument();
    restore();
  });

  it("shows empty state when no active Catalog exists", async () => {
    const restore = installFetchMock(defaultCatalogHandlers({ actives: [] }));
    render(<CatalogExplorer />);
    expect(await screen.findByText("활성 Catalog가 없습니다.")).toBeInTheDocument();
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
    expect(await screen.findByText("테이블 개요")).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Active Catalog source"), "oracle_demis_other");
    await waitFor(() => {
      expect(screen.queryByText("테이블 개요")).not.toBeInTheDocument();
    });
    expect(screen.getByText(/왼쪽 목록에서 테이블을 선택하면/i)).toBeInTheDocument();
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
    expect(screen.queryByText("테이블 개요")).not.toBeInTheDocument();
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
    expect(within(categories).getByText(/등록된 분류 정보가 없습니다/i)).toBeInTheDocument();
    expect(screen.queryByText("Stale Category Name")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /TB_ADM_HIST/i }));
    expect(await screen.findByText("테이블 개요")).toBeInTheDocument();
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
