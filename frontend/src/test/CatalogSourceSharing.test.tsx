import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataDiscoveryPortal } from "../components/DataDiscoveryPortal";
import { CatalogExplorer } from "../components/CatalogExplorer";
import { CatalogSourceProvider } from "../components/CatalogSourceContext";
import { CATALOG_SOURCE_STORAGE_KEY } from "../hooks/useCatalogSourceSelection";
import {
  activeSource,
  defaultCatalogHandlers,
  installFetchMock,
  jsonResponse,
  secondSource,
} from "./mocks";

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("shared active Catalog Source in the Discovery workspace", () => {
  it("keeps one toolbar selection across Search, Table, ERD and Index tabs", async () => {
    const user = userEvent.setup();
    const paths: string[] = [];
    const restore = installFetchMock(
      [
        (url) => { paths.push(url.pathname); return null; },
        ...defaultCatalogHandlers({ actives: [activeSource, secondSource] }),
      ],
    );

    render(<DataDiscoveryPortal />);
    expect(screen.getByRole("tab", { name: "스키마 검색" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "테이블 탐색" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "ERD 관계도" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "검색 인덱스 상태" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "스키마 변경 이력" })).toBeInTheDocument();
    const selector = await screen.findByTestId("catalog-source-toolbar-select");
    expect(selector).toHaveValue(activeSource.source_name);
    expect(screen.getAllByLabelText("Active Catalog source")).toHaveLength(1);

    await user.click(screen.getByTestId("dd-tab-explorer"));
    expect(await screen.findByRole("heading", { name: "테이블 탐색" })).toBeInTheDocument();
    expect(screen.queryByTestId("active-catalog-status")).not.toBeInTheDocument();
    expect(screen.getByTestId("toolbar-catalog-metadata")).toHaveTextContent("개정번호");
    await user.selectOptions(selector, secondSource.source_name);
    expect(selector).toHaveValue(secondSource.source_name);
    expect(screen.getAllByLabelText("Active Catalog source")).toHaveLength(1);

    await user.click(screen.getByTestId("dd-tab-erd"));
    expect(await screen.findByTestId("active-catalog-erd-explorer")).toBeInTheDocument();
    expect(screen.queryByTestId("active-catalog-status")).not.toBeInTheDocument();
    expect(selector).toHaveValue(secondSource.source_name);

    await user.click(screen.getByTestId("dd-tab-search"));
    expect(await screen.findByTestId("schema-search")).toBeInTheDocument();
    expect(selector).toHaveValue(secondSource.source_name);
    expect(screen.getAllByLabelText("Active Catalog source")).toHaveLength(1);

    await user.click(screen.getByTestId("dd-tab-index"));
    expect(await screen.findByTestId("data-discovery-index-status")).toBeInTheDocument();
    expect(screen.queryByText("활성 Catalog 정보")).not.toBeInTheDocument();
    expect(selector).toHaveValue(secondSource.source_name);
    expect(screen.getAllByLabelText("Active Catalog source")).toHaveLength(1);

    await user.click(screen.getByTestId("dd-tab-explorer"));
    expect(selector).toHaveValue(secondSource.source_name);
    expect(paths).toContain("/api/v1/catalog/active");
    expect(paths.some((path) => path.includes("connection-profiles"))).toBe(false);
    restore();
  });

  it("restores a stored candidate only after /catalog/active revalidation", async () => {
    sessionStorage.setItem(CATALOG_SOURCE_STORAGE_KEY, secondSource.source_name);
    const restore = installFetchMock([
      (url) => {
        if (url.pathname === "/api/v1/catalog/active") {
          return jsonResponse([activeSource, secondSource]);
        }
        return null;
      },
      ...defaultCatalogHandlers(),
    ]);

    render(
      <CatalogSourceProvider>
        <CatalogExplorer />
      </CatalogSourceProvider>,
    );

    await waitFor(() => {
      expect(screen.getByLabelText("Active Catalog source")).toHaveValue(
        secondSource.source_name,
      );
    });
    expect(sessionStorage.getItem(CATALOG_SOURCE_STORAGE_KEY)).toBe(secondSource.source_name);
    restore();
  });

  it("discards a stale stored candidate that is no longer in the active list", async () => {
    sessionStorage.setItem(CATALOG_SOURCE_STORAGE_KEY, "gone_source");
    const restore = installFetchMock(defaultCatalogHandlers());

    render(
      <CatalogSourceProvider>
        <CatalogExplorer />
      </CatalogSourceProvider>,
    );

    expect(await screen.findByTestId("active-catalog-status")).toBeInTheDocument();
    expect(screen.getByTestId("catalog-source-single")).toHaveTextContent(activeSource.source_name);
    expect(sessionStorage.getItem(CATALOG_SOURCE_STORAGE_KEY)).toBe(activeSource.source_name);
    restore();
  });

  it("shows empty UX when no active Catalog sources are available", async () => {
    const restore = installFetchMock([
      (url) => (url.pathname === "/api/v1/catalog/active" ? jsonResponse([]) : null),
    ]);
    render(
      <CatalogSourceProvider>
        <CatalogExplorer />
      </CatalogSourceProvider>,
    );
    expect(await screen.findByTestId("catalog-source-empty")).toBeInTheDocument();
    expect(screen.getByText(/활성 Catalog가 없습니다/)).toBeInTheDocument();
    restore();
  });

  it("surfaces Catalog read permission errors without using Connection Profile APIs", async () => {
    const seen: string[] = [];
    const restore = installFetchMock([
      (url) => {
        seen.push(url.pathname);
        if (url.pathname === "/api/v1/catalog/active") {
          return jsonResponse(
            { detail: { code: "FORBIDDEN", message: "CATALOG_READ required" } },
            403,
          );
        }
        return null;
      },
    ]);
    render(
      <CatalogSourceProvider>
        <CatalogExplorer />
      </CatalogSourceProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("HTTP 403");
    expect(screen.getByRole("alert")).toHaveTextContent("FORBIDDEN");
    expect(seen.every((path) => !path.includes("/connection-profiles"))).toBe(true);
    expect(seen.some((path) => path === "/api/v1/catalog/active")).toBe(true);
    restore();
  });

  it("automatically follows the shared Catalog selection on Snapshot History without a search form", async () => {
    const user = userEvent.setup();
    const requestedSources: string[] = [];
    const restore = installFetchMock([
      (url) => {
        if (url.pathname !== "/api/v1/schema-inspector/snapshots") return null;
        requestedSources.push(url.searchParams.get("source_name") ?? "");
        return jsonResponse([]);
      },
      ...defaultCatalogHandlers({ actives: [activeSource, secondSource] }),
    ]);
    render(<DataDiscoveryPortal />);

    await user.click(screen.getByTestId("dd-tab-explorer"));
    const selector = await screen.findByLabelText("Active Catalog source");
    await user.selectOptions(selector, secondSource.source_name);

    await user.click(screen.getByTestId("dd-tab-snapshot"));
    expect(await screen.findByTestId("snapshot-selected-source")).toHaveTextContent(secondSource.source_name);
    expect(selector).toHaveValue(secondSource.source_name);
    expect(selector).toBeEnabled();
    expect(await screen.findByRole("heading", { name: /스키마 변경 이력/ })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Snapshot source name" })).not.toBeInTheDocument();
    await waitFor(() => expect(requestedSources).toContain(secondSource.source_name));

    await user.selectOptions(selector, activeSource.source_name);
    expect(await screen.findByTestId("snapshot-selected-source")).toHaveTextContent(activeSource.source_name);
    await waitFor(() => expect(requestedSources).toContain(activeSource.source_name));

    await user.click(screen.getByTestId("dd-tab-search"));
    expect(selector).toHaveValue(activeSource.source_name);
    expect(selector).toBeEnabled();
    restore();
  });

  it("does not expose a stale unauthorized Source in the shared toolbar", async () => {
    sessionStorage.setItem(CATALOG_SOURCE_STORAGE_KEY, secondSource.source_name);
    const restore = installFetchMock(defaultCatalogHandlers());
    render(<DataDiscoveryPortal />);

    await waitFor(() => {
      expect(screen.getByTestId("catalog-source-toolbar-select")).toHaveValue(
        activeSource.source_name,
      );
    });
    expect(screen.getAllByLabelText("Active Catalog source")).toHaveLength(1);
    expect(sessionStorage.getItem(CATALOG_SOURCE_STORAGE_KEY)).toBe(activeSource.source_name);
    restore();
  });
});
