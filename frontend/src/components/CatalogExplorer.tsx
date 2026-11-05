import { useState } from "react";
import { useCatalogExplorer } from "../hooks/useCatalogExplorer";
import { useOptionalErdFocus } from "../hooks/erdFocusContext";
import { FocusedErdPanel } from "./FocusedErdPanel";
import { ActiveCatalogHeader, SourceSelector } from "./ActiveCatalogHeader";
import { useCatalogSource, useOptionalCatalogSource } from "../hooks/catalogSourceContext";
import { CatalogSourceProvider } from "./CatalogSourceContext";
import { CategoriesPanel, TableDetailPanel } from "./TableDetail";
import { StatusBanner } from "./StatusBanner";
import { TableList } from "./TableList";

function CatalogExplorerBody({ sharedSourceBar = false }: { sharedSourceBar?: boolean }) {
  const sourceSelection = useCatalogSource();
  const explorer = useCatalogExplorer(sourceSelection);
  const erdFocus = useOptionalErdFocus();
  const [showErd, setShowErd] = useState(false);
  const schemas = [...new Set(explorer.tables.map((table) => table.schema_name))].sort();
  const selectedIsVisible = Boolean(explorer.selectedTable && explorer.tablesState.status === "ready");
  const detailIsCurrent = Boolean(
    selectedIsVisible && explorer.selectedTable && explorer.detail && explorer.active &&
    explorer.active.source_name === explorer.selectedSource &&
    explorer.selectedTable.schema_name === explorer.detail.schema_name &&
    explorer.selectedTable.name === explorer.detail.name,
  );
  const sourceGate = explorer.sourcesState.status === "ready"
    ? explorer.pointerState
    : explorer.sourcesState;

  return (
    <div className="app-shell catalog-explorer-shell" data-testid="catalog-explorer">
      <header className="app-header">
        <div className="app-title-row">
          <h1>테이블 탐색</h1>
          <span className="subtitle">활성 Catalog에 등록된 테이블·컬럼·관계·인덱스·분류 정보</span>
        </div>
        {!sharedSourceBar ? <SourceSelector
          sources={explorer.sources}
          selectedSource={explorer.selectedSource}
          onSelect={explorer.selectSource}
          disabled={explorer.sourcesState.status === "loading"}
          emptyLabel="선택 가능한 활성 Catalog Source가 없습니다"
        /> : null}
        {sourceGate.status === "loading" ||
        sourceGate.status === "error" ||
        sourceGate.status === "empty" ? (
          <StatusBanner state={sourceGate} emptyLabel="활성 Catalog가 없습니다." />
        ) : (
          sharedSourceBar ? (
            explorer.staleWarning ? <div className="banner banner-warn">{explorer.staleWarning}</div> : null
          ) : (
            <ActiveCatalogHeader active={explorer.active} staleWarning={explorer.staleWarning} />
          )
        )}
      </header>

      {explorer.sourcesState.status === "ready" &&
      explorer.pointerState.status === "ready" &&
      explorer.selectedSource &&
      explorer.active ? (
        <>
          <div className="explorer-toolbar" aria-label="Table Explorer 필터">
            <label>
              분류(Category)
              <select aria-label="Category 필터" value={explorer.categoryFilter}
                disabled={explorer.categoriesState.status !== "ready" || explorer.categories.length === 0}
                onChange={(event) => explorer.setCategoryFilter(event.target.value)}>
                <option value="">전체 분류</option>
                {explorer.categories.map((category) => (
                  <option key={category.id} value={category.id}>{category.name ?? category.id}</option>
                ))}
              </select>
            </label>
            <label>
              스키마(Schema)
              <input aria-label="Schema 필터" list="catalog-schema-suggestions"
                placeholder="전체 스키마 (직접 입력 가능)"
                value={explorer.schemaFilter}
                onChange={(event) => explorer.setSchemaFilter(event.target.value)} />
              <datalist id="catalog-schema-suggestions">
                {schemas.map((schema) => <option key={schema} value={schema} />)}
              </datalist>
            </label>
            <div className="explorer-table-count" role="status">
              <strong>{explorer.tables.length}</strong>개 테이블 표시
              {explorer.tableTotal != null && explorer.tableTotal > explorer.tables.length
                ? <span> (서버 검색 총 {explorer.tableTotal}건)</span> : null}
            </div>
          </div>
          {explorer.categoriesState.status === "empty" ? (
            <p className="dd-inline-note" role="status" data-testid="catalog-category-empty-guidance">
              현재 Catalog에는 분류 정보가 등록되지 않았습니다. 분류 필터만 사용할 수 없으며 테이블·컬럼·관계 탐색은 정상적으로 이용할 수 있습니다.
            </p>
          ) : null}
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
                  onOpenFullErd={erdFocus && explorer.selectedTable ? () => {
                    erdFocus.requestErdFocus({
                      sourceName: explorer.selectedSource,
                      schemaName: explorer.selectedTable!.schema_name,
                      tableName: explorer.selectedTable!.name,
                      hops: 1,
                    });
                  } : undefined}
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

export function CatalogExplorer({ sharedSourceBar = false }: { sharedSourceBar?: boolean }) {
  const shared = useOptionalCatalogSource();
  if (!shared) {
    return (
      <CatalogSourceProvider>
        <CatalogExplorerBody sharedSourceBar={sharedSourceBar} />
      </CatalogSourceProvider>
    );
  }
  return <CatalogExplorerBody sharedSourceBar={sharedSourceBar} />;
}
