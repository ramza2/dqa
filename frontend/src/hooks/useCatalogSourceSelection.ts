import { useCallback, useEffect, useRef, useState } from "react";
import { listActiveCatalogs } from "../api/catalog";
import { CatalogApiError, type CatalogActiveSummary } from "../types/catalog";
import type { LoadState } from "../types/loadState";

/** sessionStorage candidate only — never trusted until revalidated against /catalog/active. */
export const CATALOG_SOURCE_STORAGE_KEY = "dqa.discovery.selectedCatalogSource";

export interface CatalogSourceSelection {
  sources: CatalogActiveSummary[];
  selectedSource: string;
  selectSource: (sourceName: string) => void;
  sourcesState: LoadState;
  reloadSources: () => Promise<void>;
}

function errorState(err: unknown): LoadState {
  if (err instanceof CatalogApiError) {
    return {
      status: "error",
      message: err.message,
      code: err.code,
      httpStatus: err.status,
    };
  }
  return {
    status: "error",
    message: err instanceof Error ? err.message : "Unexpected error",
    code: null,
    httpStatus: null,
  };
}

export function readStoredCatalogSourceCandidate(): string | null {
  try {
    const value = sessionStorage.getItem(CATALOG_SOURCE_STORAGE_KEY);
    return value && value.trim() ? value.trim() : null;
  } catch {
    return null;
  }
}

export function writeStoredCatalogSourceCandidate(sourceName: string | null): void {
  try {
    if (!sourceName) {
      sessionStorage.removeItem(CATALOG_SOURCE_STORAGE_KEY);
      return;
    }
    sessionStorage.setItem(CATALOG_SOURCE_STORAGE_KEY, sourceName);
  } catch {
    // Ignore quota / private-mode failures; in-memory selection still works.
  }
}

/**
 * Resolve the selectable source after a fresh active-catalog list response.
 * A stored candidate is restored only when it is still present in the
 * permission-filtered active list from the server.
 */
export function resolveCatalogSourceSelection(
  sources: CatalogActiveSummary[],
  preferred: string | null | undefined,
): string {
  if (sources.length === 0) {
    return "";
  }
  if (preferred && sources.some((item) => item.source_name === preferred)) {
    return preferred;
  }
  return sources[0].source_name;
}

/**
 * Shared Catalog Source selection for schema/Catalog discovery views.
 * Uses only GET /catalog/active (not Connection Profile APIs).
 */
export function useCatalogSourceSelection(): CatalogSourceSelection {
  const [sources, setSources] = useState<CatalogActiveSummary[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>("");
  const [sourcesState, setSourcesState] = useState<LoadState>({
    status: "loading",
    message: null,
    code: null,
    httpStatus: null,
  });
  const selectedSourceRef = useRef(selectedSource);
  selectedSourceRef.current = selectedSource;

  const applySelection = useCallback((sourceName: string, persist: boolean) => {
    setSelectedSource(sourceName);
    if (persist) {
      writeStoredCatalogSourceCandidate(sourceName || null);
    }
  }, []);

  const loadSources = useCallback(async () => {
    setSourcesState({ status: "loading", message: null, code: null, httpStatus: null });
    try {
      const list = await listActiveCatalogs();
      setSources(list);
      if (list.length === 0) {
        applySelection("", true);
        setSourcesState({
          status: "empty",
          message: "활성 Catalog가 없습니다.",
          code: null,
          httpStatus: null,
        });
        return;
      }
      const restored = resolveCatalogSourceSelection(
        list,
        readStoredCatalogSourceCandidate() ?? selectedSourceRef.current,
      );
      applySelection(restored, true);
      setSourcesState({ status: "ready", message: null, code: null, httpStatus: null });
    } catch (err) {
      setSources([]);
      applySelection("", true);
      setSourcesState(errorState(err));
    }
  }, [applySelection]);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  const selectSource = useCallback(
    (sourceName: string) => {
      if (!sourceName) {
        applySelection("", true);
        return;
      }
      if (!sources.some((item) => item.source_name === sourceName)) {
        return;
      }
      applySelection(sourceName, true);
    },
    [applySelection, sources],
  );

  return {
    sources,
    selectedSource,
    selectSource,
    sourcesState,
    reloadSources: loadSources,
  };
}
