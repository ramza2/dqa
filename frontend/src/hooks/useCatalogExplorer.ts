import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as catalogApi from "../api/catalog";
import { useDebouncedValue } from "./useDebouncedValue";
import { mergeDirectedRelations } from "../utils/relations";
import {
  assertSameSnapshot,
  matchesActive,
  type QueryMeta,
} from "../utils/revision";
import {
  CatalogApiError,
  type CatalogActiveSummary,
  type CatalogCategoryItem,
  type CatalogColumnItem,
  type CatalogIndexItem,
  type CatalogTableDetail,
  type CatalogTableItem,
  type DirectedRelation,
} from "../types/catalog";

export interface LoadState {
  status: "idle" | "loading" | "ready" | "error" | "empty";
  message: string | null;
  code: string | null;
  httpStatus: number | null;
}

const STALE_MESSAGE = "Catalog revision changed. Refreshing metadata…";

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

function tableKey(schemaName: string, tableName: string): string {
  return `${schemaName}.${tableName}`;
}

export function useCatalogExplorer() {
  const [sources, setSources] = useState<CatalogActiveSummary[]>([]);
  const [selectedSource, setSelectedSource] = useState<string>("");
  const [active, setActive] = useState<CatalogActiveSummary | null>(null);
  const [sourcesState, setSourcesState] = useState<LoadState>({
    status: "loading",
    message: null,
    code: null,
    httpStatus: null,
  });

  const [tableQuery, setTableQuery] = useState("");
  const debouncedQuery = useDebouncedValue(tableQuery, 300);
  const [tables, setTables] = useState<CatalogTableItem[]>([]);
  const [tablesState, setTablesState] = useState<LoadState>({
    status: "idle",
    message: null,
    code: null,
    httpStatus: null,
  });
  const [selectedTableKey, setSelectedTableKey] = useState<string | null>(null);

  const [detail, setDetail] = useState<CatalogTableDetail | null>(null);
  const [columns, setColumns] = useState<CatalogColumnItem[]>([]);
  const [relations, setRelations] = useState<DirectedRelation[]>([]);
  const [indexes, setIndexes] = useState<CatalogIndexItem[]>([]);
  const [categories, setCategories] = useState<CatalogCategoryItem[]>([]);
  const [detailState, setDetailState] = useState<LoadState>({
    status: "idle",
    message: null,
    code: null,
    httpStatus: null,
  });
  const [categoriesState, setCategoriesState] = useState<LoadState>({
    status: "idle",
    message: null,
    code: null,
    httpStatus: null,
  });

  const [staleWarning, setStaleWarning] = useState<string | null>(null);
  const refreshGuard = useRef(false);
  const refreshedForActiveRevision = useRef<number | null>(null);
  const lastActiveRevisionRef = useRef<number | null>(null);
  const convergedLoads = useRef({ tables: false, categories: false });
  const selectedSourceRef = useRef(selectedSource);
  selectedSourceRef.current = selectedSource;

  const selectedTable = useMemo(() => {
    if (!selectedTableKey) {
      return null;
    }
    return tables.find((t) => tableKey(t.schema_name, t.name) === selectedTableKey) ?? null;
  }, [selectedTableKey, tables]);

  const refreshActive = useCallback(async (sourceName: string) => {
    const summary = await catalogApi.getActiveCatalog(sourceName);
    if (selectedSourceRef.current !== sourceName) {
      return summary;
    }
    setActive(summary);
    return summary;
  }, []);

  const clearWarningIfConverged = useCallback(() => {
    if (convergedLoads.current.tables && convergedLoads.current.categories) {
      setStaleWarning(null);
      // Full convergence: allow a future refresh only after the next real revision change
      // or a later full stale cycle for a new active revision.
      refreshedForActiveRevision.current = null;
    }
  }, []);

  const handleStaleSnapshot = useCallback(
    async (sourceName: string, currentActiveRevision: number) => {
      convergedLoads.current = { tables: false, categories: false };
      setStaleWarning(STALE_MESSAGE);
      if (refreshGuard.current) {
        return;
      }
      if (selectedSourceRef.current !== sourceName) {
        return;
      }
      // One guarded refresh per observed active revision to avoid infinite loops
      // when query responses remain stale after refresh.
      if (refreshedForActiveRevision.current === currentActiveRevision) {
        return;
      }
      refreshGuard.current = true;
      refreshedForActiveRevision.current = currentActiveRevision;
      try {
        await refreshActive(sourceName);
      } finally {
        refreshGuard.current = false;
      }
    },
    [refreshActive],
  );

  const acceptSnapshot = useCallback(
    async (
      meta: QueryMeta,
      sourceName: string,
      current: CatalogActiveSummary,
    ): Promise<boolean> => {
      if (selectedSourceRef.current !== sourceName) {
        return false;
      }
      if (!matchesActive(meta, current, sourceName)) {
        await handleStaleSnapshot(sourceName, current.revision_id);
        return false;
      }
      // Do not reset refreshedForActiveRevision here: a healthy tables response must not
      // unlock another refresh while categories (or another endpoint) stay stale on the
      // same active revision.
      return true;
    },
    [handleStaleSnapshot],
  );

  const loadSources = useCallback(async () => {
    setSourcesState({ status: "loading", message: null, code: null, httpStatus: null });
    try {
      const list = await catalogApi.listActiveCatalogs();
      setSources(list);
      if (list.length === 0) {
        setSelectedSource("");
        setActive(null);
        setSourcesState({
          status: "empty",
          message: "No active Catalog",
          code: null,
          httpStatus: null,
        });
        return;
      }
      setSourcesState({ status: "ready", message: null, code: null, httpStatus: null });
      setSelectedSource((prev) => {
        if (prev && list.some((item) => item.source_name === prev)) {
          return prev;
        }
        return list[0].source_name;
      });
    } catch (err) {
      setSources([]);
      setSelectedSource("");
      setActive(null);
      setSourcesState(errorState(err));
    }
  }, []);

  useEffect(() => {
    void loadSources();
  }, [loadSources]);

  // Source change: reset selection and resolve the active pointer for that source only.
  useEffect(() => {
    if (!selectedSource) {
      setActive(null);
      setTables([]);
      setSelectedTableKey(null);
      setDetail(null);
      setColumns([]);
      setRelations([]);
      setIndexes([]);
      setCategories([]);
      setStaleWarning(null);
      return;
    }

    let cancelled = false;
    setSelectedTableKey(null);
    setDetail(null);
    setColumns([]);
    setRelations([]);
    setIndexes([]);
    setCategories([]);
    setTableQuery("");
    setStaleWarning(null);
    setActive(null);
    refreshedForActiveRevision.current = null;
    lastActiveRevisionRef.current = null;
    convergedLoads.current = { tables: false, categories: false };

    (async () => {
      try {
        const summary = await catalogApi.getActiveCatalog(selectedSource);
        if (cancelled || selectedSourceRef.current !== selectedSource) {
          return;
        }
        lastActiveRevisionRef.current = summary.revision_id;
        setActive(summary);
      } catch (err) {
        if (!cancelled && selectedSourceRef.current === selectedSource) {
          setActive(null);
          setSourcesState(errorState(err));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedSource]);

  // Real active revision change (e.g. rev2 -> rev3): allow one guarded refresh for the new revision.
  useEffect(() => {
    if (!active) {
      return;
    }
    if (
      lastActiveRevisionRef.current !== null &&
      lastActiveRevisionRef.current !== active.revision_id
    ) {
      refreshedForActiveRevision.current = null;
    }
    lastActiveRevisionRef.current = active.revision_id;
  }, [active]);

  // Tables: reload whenever active revision (or search) changes.
  useEffect(() => {
    if (!selectedSource || !active || active.source_name !== selectedSource) {
      return;
    }
    let cancelled = false;
    const expectedSource = selectedSource;
    const expectedActive = active;
    setTablesState({ status: "loading", message: null, code: null, httpStatus: null });

    (async () => {
      try {
        const response = await catalogApi.listTables(expectedSource, {
          q: debouncedQuery || undefined,
          limit: 500,
        });
        if (cancelled || selectedSourceRef.current !== expectedSource) {
          return;
        }
        const accepted = await acceptSnapshot(response, expectedSource, expectedActive);
        if (!accepted || cancelled || selectedSourceRef.current !== expectedSource) {
          return;
        }
        setTables(response.items);
        convergedLoads.current.tables = true;
        clearWarningIfConverged();
        setTablesState(
          response.items.length === 0
            ? {
                status: "empty",
                message: "No tables match this search",
                code: null,
                httpStatus: null,
              }
            : { status: "ready", message: null, code: null, httpStatus: null },
        );
        setSelectedTableKey((prev) => {
          if (!prev) {
            return null;
          }
          const stillThere = response.items.some(
            (item) => tableKey(item.schema_name, item.name) === prev,
          );
          return stillThere ? prev : null;
        });
      } catch (err) {
        if (!cancelled && selectedSourceRef.current === expectedSource) {
          setTables([]);
          setTablesState(errorState(err));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedSource, debouncedQuery, active, acceptSnapshot, clearWarningIfConverged]);

  // Categories: same active revision dependency as tables.
  useEffect(() => {
    if (!selectedSource || !active || active.source_name !== selectedSource) {
      return;
    }
    let cancelled = false;
    const expectedSource = selectedSource;
    const expectedActive = active;
    setCategoriesState({ status: "loading", message: null, code: null, httpStatus: null });

    (async () => {
      try {
        const response = await catalogApi.listCategories(expectedSource, { limit: 500 });
        if (cancelled || selectedSourceRef.current !== expectedSource) {
          return;
        }
        const accepted = await acceptSnapshot(response, expectedSource, expectedActive);
        if (!accepted || cancelled || selectedSourceRef.current !== expectedSource) {
          // Do not commit stale category rows.
          return;
        }
        setCategories(response.items);
        convergedLoads.current.categories = true;
        clearWarningIfConverged();
        setCategoriesState(
          response.items.length === 0
            ? {
                status: "empty",
                message: "No categories in this Catalog",
                code: null,
                httpStatus: null,
              }
            : { status: "ready", message: null, code: null, httpStatus: null },
        );
      } catch (err) {
        if (!cancelled && selectedSourceRef.current === expectedSource) {
          setCategories([]);
          setCategoriesState(errorState(err));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedSource, active, acceptSnapshot, clearWarningIfConverged]);

  // Detail batch: all responses must share one snapshot, then match active.
  useEffect(() => {
    if (!selectedSource || !active || active.source_name !== selectedSource || !selectedTable) {
      setDetail(null);
      setColumns([]);
      setRelations([]);
      setIndexes([]);
      setDetailState({ status: "idle", message: null, code: null, httpStatus: null });
      return;
    }

    let cancelled = false;
    const expectedSource = selectedSource;
    const expectedActive = active;
    const expectedTable = selectedTable;
    setDetailState({ status: "loading", message: null, code: null, httpStatus: null });

    (async () => {
      try {
        const [detailResponse, columnsResponse, outgoing, incoming, indexesResponse] =
          await Promise.all([
            catalogApi.getTableDetail(
              expectedSource,
              expectedTable.schema_name,
              expectedTable.name,
            ),
            catalogApi.listColumns(expectedSource, {
              schema_name: expectedTable.schema_name,
              table_name: expectedTable.name,
              limit: 500,
            }),
            catalogApi.listRelations(expectedSource, {
              schema_name: expectedTable.schema_name,
              table_name: expectedTable.name,
              limit: 500,
            }),
            catalogApi.listRelations(expectedSource, {
              referenced_table_name: expectedTable.name,
              limit: 500,
            }),
            catalogApi.listIndexes(expectedSource, {
              schema_name: expectedTable.schema_name,
              table_name: expectedTable.name,
              limit: 500,
            }),
          ]);

        if (cancelled || selectedSourceRef.current !== expectedSource) {
          return;
        }

        const batchMeta = assertSameSnapshot([
          detailResponse,
          columnsResponse,
          outgoing,
          incoming,
          indexesResponse,
        ]);
        if (!batchMeta) {
          await handleStaleSnapshot(expectedSource, expectedActive.revision_id);
          return;
        }

        const accepted = await acceptSnapshot(batchMeta, expectedSource, expectedActive);
        if (!accepted || cancelled || selectedSourceRef.current !== expectedSource) {
          return;
        }

        setDetail(detailResponse.item);
        setColumns(columnsResponse.items);
        setRelations(
          mergeDirectedRelations(
            outgoing.items,
            incoming.items,
            expectedTable.schema_name,
          ),
        );
        setIndexes(indexesResponse.items);
        setDetailState({ status: "ready", message: null, code: null, httpStatus: null });
        clearWarningIfConverged();
      } catch (err) {
        if (!cancelled && selectedSourceRef.current === expectedSource) {
          setDetail(null);
          setColumns([]);
          setRelations([]);
          setIndexes([]);
          setDetailState(errorState(err));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedSource, selectedTable, active, acceptSnapshot, handleStaleSnapshot, clearWarningIfConverged]);

  const selectSource = (sourceName: string) => {
    setSelectedSource(sourceName);
  };

  const selectTable = (schemaName: string, tableName: string) => {
    setSelectedTableKey(tableKey(schemaName, tableName));
  };

  return {
    sources,
    selectedSource,
    selectSource,
    active,
    sourcesState,
    tableQuery,
    setTableQuery,
    tables,
    tablesState,
    selectedTable,
    selectTable,
    detail,
    columns,
    relations,
    indexes,
    categories,
    detailState,
    categoriesState,
    staleWarning,
    reloadSources: loadSources,
  };
}
