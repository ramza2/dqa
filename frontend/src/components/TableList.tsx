import type { CatalogTableItem } from "../types/catalog";
import type { LoadState } from "../hooks/useCatalogExplorer";
import { StatusBanner } from "./StatusBanner";

interface Props {
  query: string;
  onQueryChange: (value: string) => void;
  tables: CatalogTableItem[];
  selectedKey: string | null;
  onSelect: (schemaName: string, tableName: string) => void;
  state: LoadState;
}

export function TableList({
  query,
  onQueryChange,
  tables,
  selectedKey,
  onSelect,
  state,
}: Props) {
  return (
    <aside className="pane" aria-label="Table explorer">
      <div className="pane-header">
        <h2>Tables</h2>
        <input
          className="search-input"
          type="search"
          placeholder="Search tables (name or comment)"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          aria-label="Search tables"
        />
      </div>
      {state.status === "loading" || state.status === "error" || state.status === "empty" ? (
        <div style={{ padding: "0.85rem" }}>
          <StatusBanner state={state} emptyLabel="No tables" />
        </div>
      ) : null}
      <ul className="table-list">
        {tables.map((table) => {
          const key = `${table.schema_name}.${table.name}`;
          const selected = key === selectedKey;
          return (
            <li key={key}>
              <button
                type="button"
                className={`table-list-item${selected ? " selected" : ""}`}
                onClick={() => onSelect(table.schema_name, table.name)}
              >
                <div className="schema">{table.schema_name}</div>
                <div className="name">{table.name}</div>
                {table.comment ? <div className="comment">{table.comment}</div> : null}
                <div className="chip-row" style={{ marginTop: "0.35rem" }}>
                  {table.table_type ? (
                    <span className="badge badge-muted">{table.table_type}</span>
                  ) : null}
                  {table.category_ids.map((id) => (
                    <span key={id} className="badge badge-muted">
                      {id}
                    </span>
                  ))}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
