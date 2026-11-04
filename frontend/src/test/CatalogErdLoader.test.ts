import { afterEach, describe, expect, it } from "vitest";
import { loadActiveCatalogErd } from "../api/catalogErd";
import {
  activeSource, defaultCatalogHandlers, installFetchMock, jsonResponse,
  tablesResponse,
} from "./mocks";

let restore: (() => void) | null = null;
afterEach(() => { restore?.(); restore = null; });

describe("bounded active Catalog ERD loader", () => {
  it("reads revision-pinned metadata without Oracle or mutation calls", async () => {
    const methods: string[] = [];
    restore = installFetchMock([
      (url, init) => { methods.push((init?.method ?? "GET") + " " + url.pathname); return null; },
      ...defaultCatalogHandlers(),
    ]);
    const result = await loadActiveCatalogErd("oracle_demis_mock");
    expect(result.active).toEqual(activeSource);
    expect(result.tables).toEqual(tablesResponse.items);
    expect(result.totalRelations).toBe(1);
    expect(result.truncated).toBe(false);
    expect(methods.every((entry) => entry.startsWith("GET /api/v1/catalog/"))).toBe(true);
    expect(methods.filter((entry) => entry.endsWith("/oracle_demis_mock"))).toHaveLength(2);
  });

  it("paginates a large catalog and labels remaining pages as truncated", async () => {
    const offsets: number[] = [];
    const all = Array.from({ length: 1500 }, (_, i) => ({
      ...tablesResponse.items[0], name: `TB_${String(i).padStart(4, "0")}`,
    }));
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => {
      if (!url.pathname.endsWith("/tables")) return null;
      const offset = Number(url.searchParams.get("offset") ?? "0");
      const limit = Number(url.searchParams.get("limit") ?? "500");
      offsets.push(offset);
      return jsonResponse({ ...tablesResponse, total: all.length, offset, limit,
        items: all.slice(offset, offset + limit) });
    });
    restore = installFetchMock(handlers);
    const result = await loadActiveCatalogErd("oracle_demis_mock");
    expect(offsets).toEqual([0, 500]);
    expect(result.tables).toHaveLength(1000);
    expect(result.totalTables).toBe(1500);
    expect(result.truncated).toBe(true);
  });

  it("rejects a mismatched fingerprint even if the revision number matches", async () => {
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => url.pathname.endsWith("/tables")
      ? jsonResponse({ ...tablesResponse, schema_fingerprint: "unexpected-fingerprint" }) : null);
    restore = installFetchMock(handlers);
    await expect(loadActiveCatalogErd("oracle_demis_mock"))
      .rejects.toThrow("CATALOG_ERD_REVISION_OR_PAGE_MISMATCH");
  });

  it("rejects a cross-source response even when the revision and fingerprint match", async () => {
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => url.pathname.endsWith("/tables")
      ? jsonResponse({ ...tablesResponse, source_name: "another_source" }) : null);
    restore = installFetchMock(handlers);
    await expect(loadActiveCatalogErd("oracle_demis_mock"))
      .rejects.toThrow("CATALOG_ERD_REVISION_OR_PAGE_MISMATCH");
  });

  it("rejects pointer changes after the paginated read", async () => {
    let activeRequests = 0;
    const handlers = defaultCatalogHandlers();
    handlers.unshift((url) => {
      if (url.pathname === "/api/v1/catalog/active/oracle_demis_mock") {
        activeRequests += 1;
        return jsonResponse(activeRequests === 1 ? activeSource
          : { ...activeSource, revision_id: 2 });
      }
      return null;
    });
    restore = installFetchMock(handlers);
    await expect(loadActiveCatalogErd("oracle_demis_mock"))
      .rejects.toThrow("CATALOG_ERD_ACTIVE_CHANGED");
  });
});
