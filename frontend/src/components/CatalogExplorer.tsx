import { useCatalogExplorer } from "../hooks/useCatalogExplorer";
import { ActiveCatalogHeader, SourceSelector } from "./ActiveCatalogHeader";
import { CategoriesPanel, TableDetailPanel } from "./TableDetail";
import { StatusBanner } from "./StatusBanner";
import { TableList } from "./TableList";

export function CatalogExplorer() {
  const explorer = useCatalogExplorer();

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
              <TableDetailPanel
                detail={explorer.detail}
                columns={explorer.columns}
                relations={explorer.relations}
                indexes={explorer.indexes}
                state={explorer.detailState}
              />
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
