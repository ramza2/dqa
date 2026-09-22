import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as catalogApi from "../api/catalog";
import { useDebouncedValue } from "./useDebouncedValue";
import { mergeDirectedRelations } from "../utils/relations";
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

interface QueryMeta {
  revision_id: number;
  schema_fingerprint: string;
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

  const selectedTable = useMemo(() => {
    if (!selectedTableKey) {
      return null;
    }
    return tables.find((t) => `${t.schema_name}.${t.name}` === selectedTableKey) ?? null;
  }, [selectedTableKey, tables]);

  const refreshActive = useCallback(async (sourceName: string) => {
    const summary = await catalogApi.getActiveCatalog(sourceName);
    setActive(summary);
    return summary;
  }, []);

  const checkRevisionConsistency = useCallback(
    async (meta: QueryMeta, sourceName: string, current: CatalogActiveSummary | null) => {
      if (!current || current.source_name !== sourceName) {
        return;
      }
      if (
        meta.revision_id === current.revision_id &&
        meta.schema_fingerprint === current.schema_fingerprint
      ) {
        setStaleWarning(null);
        return;
      }
      if (refreshGuard.current) {
        setStaleWarning("Catalog revision changed. Refreshing metadata…");
        return;
      }
      refreshGuard.current = true;
      setStaleWarning("Catalog revision changed. Refreshing metadata…");
      try {
        await refreshActive(sourceName);
      } finally {
        refreshGuard.current = false;
      }
    },
    [refreshActive],
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
      return;
    }

    let cancelled = false;
    setSelectedTableKey(null);
    setDetail(null);
    setColumns([]);
    setRelations([]);
    setIndexes([]);
    setTableQuery("");

    (async () => {
      try {
        const summary = await catalogApi.getActiveCatalog(selectedSource);
        if (!cancelled) {
          setActive(summary);
        }
      } catch (err) {
        if (!cancelled) {
          setActive(null);
          setSourcesState(errorState(err));
        }
      }

      try {
        if (!cancelled) {
          setCategoriesState({ status: "loading", message: null, code: null, httpStatus: null });
        }
        const response = await catalogApi.listCategories(selectedSource, { limit: 500 });
        if (cancelled) {
          return;
        }
        setCategories(response.items);
        setCategoriesState(
          response.items.length === 0
            ? { status: "empty", message: "No categories in this Catalog", code: null, httpStatus: null }
            : { status: "ready", message: null, code: null, httpStatus: null },
        );
        await checkRevisionConsistency(response, selectedSource, null);
      } catch (err) {
        if (!cancelled) {
          setCategories([]);
          setCategoriesState(errorState(err));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedSource, checkRevisionConsistency]);

  useEffect(() => {
    if (!selectedSource) {
      return;
    }
    let cancelled = false;
    setTablesState({ status: "loading", message: null, code: null, httpStatus: null });

    (async () => {
      try {
        const response = await catalogApi.listTables(selectedSource, {
          q: debouncedQuery || undefined,
          limit: 500,
        });
        if (cancelled) {
          return;
        }
        setTables(response.items);
        setTablesState(
          response.items.length === 0
            ? { status: "empty", message: "No tables match this search", code: null, httpStatus: null }
            : { status: "ready", message: null, code: null, httpStatus: null },
        );
        await checkRevisionConsistency(response, selectedSource, active);
      } catch (err) {
        if (!cancelled) {
          setTables([]);
          setTablesState(errorState(err));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [selectedSource, debouncedQuery, active, checkRevisionConsistency]);

  useEffect(() => {
    if (!selectedSource || !selectedTable) {
      setDetail(null);
      setColumns([]);
      setRelations([]);
      setIndexes([]);
      setDetailState({ status: "idle", message: null, code: null, httpStatus: null });
      return;
    }

    let cancelled = false;
    setDetailState({ status: "loading", message: null, code: null, httpStatus: null });

    (async () => {
      try {
        const [detailResponse, columnsResponse, outgoing, incoming, indexesResponse] =
          await Promise.all([
            catalogApi.getTableDetail(
              selectedSource,
              selectedTable.schema_name,
              selectedTable.name,
            ),
            catalogApi.listColumns(selectedSource, {
              schema_name: selectedTable.schema_name,
              table_name: selectedTable.name,
              limit: 500,
            }),
            catalogApi.listRelations(selectedSource, {
              schema_name: selectedTable.schema_name,
              table_name: selectedTable.name,
              limit: 500,
            }),
            catalogApi.listRelations(selectedSource, {
              referenced_table_name: selectedTable.name,
              limit: 500,
            }),
            catalogApi.listIndexes(selectedSource, {
              schema_name: selectedTable.schema_name,
              table_name: selectedTable.name,
              limit: 500,
            }),
          ]);
        if (cancelled) {
          return;
        }
        setDetail(detailResponse.item);
        setColumns(columnsResponse.items);
        setRelations(
          mergeDirectedRelations(
            outgoing.items,
            incoming.items,
            selectedTable.schema_name,
          ),
        );
        setIndexes(indexesResponse.items);
        setDetailState({ status: "ready", message: null, code: null, httpStatus: null });
        await checkRevisionConsistency(detailResponse, selectedSource, active);
      } catch (err) {
        if (!cancelled) {
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
  }, [selectedSource, selectedTable, active, checkRevisionConsistency]);

  const selectSource = (sourceName: string) => {
    setSelectedSource(sourceName);
  };

  const selectTable = (schemaName: string, tableName: string) => {
    setSelectedTableKey(`${schemaName}.${tableName}`);
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
