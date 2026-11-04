import { afterEach, describe, expect, it, vi } from "vitest";
import {
  CATALOG_SOURCE_STORAGE_KEY,
  readStoredCatalogSourceCandidate,
  resolveCatalogSourceSelection,
  writeStoredCatalogSourceCandidate,
} from "../hooks/useCatalogSourceSelection";
import { activeSource, secondSource } from "./mocks";

afterEach(() => {
  sessionStorage.clear();
  vi.restoreAllMocks();
});

describe("resolveCatalogSourceSelection", () => {
  it("returns empty when no active sources are visible", () => {
    expect(resolveCatalogSourceSelection([], "oracle_demis_mock")).toBe("");
  });

  it("auto-selects the only visible active source", () => {
    expect(resolveCatalogSourceSelection([activeSource], null)).toBe(activeSource.source_name);
  });

  it("restores a preferred source only when it remains in the permission-filtered list", () => {
    expect(
      resolveCatalogSourceSelection(
        [activeSource, secondSource],
        secondSource.source_name,
      ),
    ).toBe(secondSource.source_name);
    expect(
      resolveCatalogSourceSelection([activeSource], secondSource.source_name),
    ).toBe(activeSource.source_name);
  });

  it("falls back to the first visible source when preference is missing", () => {
    expect(resolveCatalogSourceSelection([activeSource, secondSource], null)).toBe(
      activeSource.source_name,
    );
  });
});

describe("catalog source session candidate", () => {
  it("stores and reads a candidate without treating it as authorization", () => {
    writeStoredCatalogSourceCandidate(secondSource.source_name);
    expect(sessionStorage.getItem(CATALOG_SOURCE_STORAGE_KEY)).toBe(secondSource.source_name);
    expect(readStoredCatalogSourceCandidate()).toBe(secondSource.source_name);
    writeStoredCatalogSourceCandidate(null);
    expect(readStoredCatalogSourceCandidate()).toBeNull();
  });
});
