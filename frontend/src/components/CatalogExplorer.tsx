import { useState } from "react";
import { useCatalogExplorer } from "../hooks/useCatalogExplorer";
import { FocusedErdPanel } from "./FocusedErdPanel";
import { ActiveCatalogHeader, SourceSelector } from "./ActiveCatalogHeader";
import { CategoriesPanel, TableDetailPanel } from "./TableDetail";
import { StatusBanner } from "./StatusBanner";
import { TableList } from "./TableList";

export function CatalogExplorer() {
  const explorer = useCatalogExplorer();
  const [showErd, setShowErd] = useState(false);
  const schemas = [...new Set(explorer.tables.map((table) => table.schema_name))].sort();
  const selectedIsVisible = Boolean(explorer.selectedTable && explorer.tablesState.status === "ready");
  const detailIsCurrent = Boolean(
    selectedIsVisible && explorer.selectedTable && explorer.detail && explorer.active &&
    explorer.active.source_name === explorer.selectedSource &&
    explorer.selectedTable.schema_name === explorer.detail.schema_name &&
    explorer.selectedTable.name === explorer.detail.name,
  );

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title-row">
          <h1>Table Explorer</h1>
          <span className="subtitle">활성 Catalog의 Table·Column·관계·Index·Category 탐색</span>
        </div>
        <SourceSelector
          sources={explorer.sources}
          selectedSource={explorer.selectedSource}
          onSelect={explorer.selectSource}
          disabled={explorer.sourcesState.status === "loading"}
        />
        {explorer.sourcesState.status === "loading" ||
        explorer.sourcesState.status === "error" ||
        explorer.sourcesState.status === "empty" ? (
          <StatusBanner state={explorer.sourcesState} emptyLabel="No active Catalog" />
        ) : (
          <ActiveCatalogHeader
            active={explorer.active}
            staleWarning={explorer.staleWarning}
          />
        )}
      </header>

      {explorer.sourcesState.status === "ready" && explorer.selectedSource ? (
        <>
          <div className="explorer-toolbar" aria-label="Table Explorer 필터">
            <label>
              Category
              <select aria-label="Category 필터" value={explorer.categoryFilter}
                disabled={explorer.categoriesState.status !== "ready"}
                onChange={(event) => explorer.setCategoryFilter(event.target.value)}>
                <option value="">전체 Category</option>
                {explorer.categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name ?? category.id}</option>
                ))}
              </select>
            </label>
            <label>
              Schema
              <input aria-label="Schema 필터" list="catalog-schema-suggestions"
                placeholder="전체 Schema (직접 입력 가능)"
                value={explorer.schemaFilter}
                onChange={(event) => explorer.setSchemaFilter(event.target.value)} />
              <datalist id="catalog-schema-suggestions">
                {schemas.map((schema) => <option key={schema} value={schema} />)}
              </datalist>
            </label>
            <div className="explorer-table-count" role="status">
              <strong>{explorer.tables.length}</strong> loaded tables
              {explorer.tableTotal != null && explorer.tableTotal > explorer.tables.length
                ? <span> (서버 검색 총 {explorer.tableTotal}건)</span> : null}
            </div>
          </div>
          <div className="main-layout">
            <TableList
              query={explorer.tableQuery}
              onQueryChange={explorer.setTableQuery}
              tables={explorer.tablesState.status === "ready" ? explorer.tables : []}
              selectedKey={
                explorer.selectedTable
                  ? `${explorer.selectedTable.schema_name}.${explorer.selectedTable.name}`
                  : null
              }
              onSelect={explorer.selectTable}
              state={explorer.tablesState}
              loadedCount={explorer.tables.length}
              totalCount={explorer.tableTotal ?? undefined}
              serverLoadedCount={explorer.tables.length}
            />
            <main className="pane pane-right">
              {selectedIsVisible ? (
                <div className="erd-switch" role="group" aria-label="테이블 보기 방식">
                  <button type="button" aria-pressed={!showErd}
                    onClick={() => setShowErd(false)}>상세정보</button>
                  <button type="button" aria-pressed={showErd}
                    onClick={() => setShowErd(true)}>관계 ERD</button>
                </div>
              ) : null}
              {showErd && detailIsCurrent && explorer.detailState.status === "ready" &&
               explorer.active?.source_name === explorer.selectedSource ? (
                <FocusedErdPanel
                  key={explorer.selectedSource + ":" + explorer.active.revision_id +
                    ":" + explorer.detail!.schema_name + "." + explorer.detail!.name}
                  detail={explorer.detail!}
                  relations={explorer.relations}
                  source={explorer.selectedSource}
                  revision={explorer.active.revision_id}
                />
              ) : (
                <TableDetailPanel
                  key={explorer.selectedSource + ":" + explorer.active?.revision_id + ":" +
                    (explorer.selectedTable?.schema_name ?? "") + "." +
                    (explorer.selectedTable?.name ?? "")}
                  detail={detailIsCurrent ? explorer.detail : null}
                  columns={detailIsCurrent ? explorer.columns : []}
                  relations={detailIsCurrent ? explorer.relations : []}
                  indexes={detailIsCurrent ? explorer.indexes : []}
                  categories={explorer.categories}
                  state={!selectedIsVisible && explorer.detailState.status !== "idle"
                    ? { status: "idle", message: null, code: null, httpStatus: null }
                    : detailIsCurrent || explorer.detailState.status !== "ready"
                    ? explorer.detailState
                    : { status: "loading", message: null, code: null, httpStatus: null }}
                />
              )}
              <CategoriesPanel
                categories={explorer.categories}
                state={explorer.categoriesState}
              />
            </main>
          </div>
        </>
      ) : null}
    </div>
  );
}
