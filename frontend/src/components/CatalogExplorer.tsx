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
  const detailIsCurrent = Boolean(
    explorer.selectedTable && explorer.detail && explorer.active &&
    explorer.active.source_name === explorer.selectedSource &&
    explorer.selectedTable.schema_name === explorer.detail.schema_name &&
    explorer.selectedTable.name === explorer.detail.name,
  );

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-title-row">
          <h1>DQA / Catalog Explorer</h1>
          <span className="subtitle">Active Catalog metadata browser</span>
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
          <div className="main-layout">
            <TableList
              query={explorer.tableQuery}
              onQueryChange={explorer.setTableQuery}
              tables={explorer.tables}
              selectedKey={
                explorer.selectedTable
                  ? `${explorer.selectedTable.schema_name}.${explorer.selectedTable.name}`
                  : null
              }
              onSelect={explorer.selectTable}
              state={explorer.tablesState}
            />
            <main className="pane pane-right">
              {explorer.selectedTable ? (
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
                  detail={detailIsCurrent ? explorer.detail : null}
                  columns={detailIsCurrent ? explorer.columns : []}
                  relations={detailIsCurrent ? explorer.relations : []}
                  indexes={detailIsCurrent ? explorer.indexes : []}
                  state={detailIsCurrent || explorer.detailState.status !== "ready"
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
