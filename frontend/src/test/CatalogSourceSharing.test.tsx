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

describe("shared Catalog Source across Table/ERD Explorer", () => {
  it("keeps the selected source when switching Table Explorer and ERD Explorer tabs", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      defaultCatalogHandlers({ actives: [activeSource, secondSource] }),
    );

    render(<DataDiscoveryPortal />);
    await user.click(screen.getByTestId("dd-tab-explorer"));
    expect(await screen.findByRole("heading", { name: "Table Explorer" })).toBeInTheDocument();

    const selector = await screen.findByLabelText("Active Catalog source");
    await user.selectOptions(selector, secondSource.source_name);
    expect(selector).toHaveValue(secondSource.source_name);

    await user.click(screen.getByTestId("dd-tab-erd"));
    expect(await screen.findByTestId("active-catalog-erd-explorer")).toBeInTheDocument();
    expect(await screen.findByLabelText("Active Catalog source")).toHaveValue(
      secondSource.source_name,
    );

    await user.click(screen.getByTestId("dd-tab-explorer"));
    expect(await screen.findByLabelText("Active Catalog source")).toHaveValue(
      secondSource.source_name,
    );
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
    expect(screen.getByText(/No active Catalog/i)).toBeInTheDocument();
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

  it("does not let Schema Search inherit the shared Table/ERD source selection", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      defaultCatalogHandlers({ actives: [activeSource, secondSource] }),
    );
    render(<DataDiscoveryPortal />);

    await user.click(screen.getByTestId("dd-tab-explorer"));
    const explorerSelect = await screen.findByLabelText("Active Catalog source");
    await user.selectOptions(explorerSelect, secondSource.source_name);

    await user.click(screen.getByTestId("dd-tab-search"));
    const searchSelect = await screen.findByLabelText("Active Catalog source");
    // Schema Search keeps an independent default (first source), not the shared ERD/Table pick.
    expect(searchSelect).toHaveValue(activeSource.source_name);
    restore();
  });
});
