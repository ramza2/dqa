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
  loadedCount?: number;
  totalCount?: number;
  serverLoadedCount?: number;
}

export function TableList({
  query,
  onQueryChange,
  tables,
  selectedKey,
  onSelect,
  state,
  loadedCount,
  totalCount,
  serverLoadedCount,
}: Props) {
  return (
    <aside className="pane" aria-label="Table explorer">
      <div className="pane-header">
        <div className="table-list-heading">
          <h2>테이블 목록</h2>
          {loadedCount != null ? (
            <span className="muted" aria-label="표시된 테이블 수">
              {loadedCount}건 표시
            </span>
          ) : null}
        </div>
        <input
          className="search-input"
          type="search"
          placeholder="테이블명 또는 설명 검색"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          aria-label="Search tables"
        />
        {totalCount != null && serverLoadedCount != null && totalCount > serverLoadedCount ? (
          <p className="table-list-hint" role="status">
            검색 결과 {totalCount}건 중 서버가 반환한 {serverLoadedCount}건만 탐색합니다.
            더 좁은 검색어를 입력해 주세요.
          </p>
        ) : null}
      </div>
      {state.status === "loading" || state.status === "error" || state.status === "empty" ? (
        <div className="pane-status">
          <StatusBanner state={state} emptyLabel="조건에 맞는 테이블이 없습니다." />
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
                <div className="chip-row chip-row-spaced">
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
