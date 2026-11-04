import { useState } from "react";
import type {
  CatalogCategoryItem,
  CatalogColumnItem,
  CatalogIndexItem,
  CatalogTableDetail,
  DirectedRelation,
} from "../types/catalog";
import type { LoadState } from "../hooks/useCatalogExplorer";
import { formatColumnMapping } from "../utils/relations";
import { StatusBanner } from "./StatusBanner";

interface DetailProps {
  detail: CatalogTableDetail | null;
  columns: CatalogColumnItem[];
  relations: DirectedRelation[];
  indexes: CatalogIndexItem[];
  categories?: CatalogCategoryItem[];
  state: LoadState;
}

type DetailTab = "columns" | "relations" | "indexes" | "categories";

const DETAIL_TABS: { id: DetailTab; label: string }[] = [
  { id: "columns", label: "Columns" },
  { id: "relations", label: "Relations" },
  { id: "indexes", label: "Indexes" },
  { id: "categories", label: "Categories" },
];

export function TableDetailPanel({
  detail,
  columns,
  relations,
  indexes,
  categories = [],
  state,
}: DetailProps) {
  const [tab, setTab] = useState<DetailTab>("columns");
  if (state.status === "idle") {
    return <div className="placeholder">Select a table to inspect metadata.</div>;
  }
  if (state.status === "loading" || state.status === "error") {
    return <StatusBanner state={state} />;
  }
  if (!detail) {
    return <div className="placeholder">No table detail available.</div>;
  }

  const outbound = relations.filter((relation) => relation.direction === "OUT");
  const inbound = relations.filter((relation) => relation.direction === "IN");
  const matchingCategories = categories.filter((category) =>
    detail.category_ids.includes(category.id) ||
    category.assignments.some((assignment) =>
      assignment.table_name === detail.name &&
      assignment.schema_name === detail.schema_name,
    ),
  );
  // The active table detail is authoritative even when the bounded category list
  // omits a category name or its assignment metadata.
  const tableCategories = [
    ...matchingCategories,
    ...detail.category_ids.filter((id) => !matchingCategories.some((item) => item.id === id))
      .map((id) => ({ id, name: null, description: null, assignments: [] })),
  ];

  const relationTable = (items: DirectedRelation[], direction: "OUT" | "IN") => (
    items.length === 0 ? (
      <p className="placeholder">{direction === "OUT" ? "나가는 FK" : "들어오는 FK"}가 없습니다.</p>
    ) : (
      <div className="table-scroll">
        <table className="data-table">
          <thead><tr><th>Constraint</th><th>Related Table</th><th>Column Mapping</th></tr></thead>
          <tbody>
            {items.map((relation) => (
              <tr key={relation.key}>
                <td className="mono">{relation.name ?? "—"}</td>
                <td className="mono">
                  {direction === "OUT"
                    ? [relation.targetSchema, relation.targetTable].filter(Boolean).join(".")
                    : [relation.sourceSchema, relation.sourceTable].filter(Boolean).join(".")}
                </td>
                <td className="mono">{formatColumnMapping(relation.columns)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  );

  return (
    <div className="table-detail-workspace">
      <section className="section" aria-label="Table overview">
        <h3>Overview</h3>
        <p className="table-detail-title mono">{detail.schema_name}.{detail.name}</p>
        <div className="meta-grid">
          <div className="meta-card">
            <div className="label">Schema</div>
            <div className="value">{detail.schema_name}</div>
          </div>
          <div className="meta-card">
            <div className="label">Table</div>
            <div className="value">{detail.name}</div>
          </div>
          <div className="meta-card">
            <div className="label">Type</div>
            <div className="value">{detail.table_type ?? "—"}</div>
          </div>
          <div className="meta-card">
            <div className="label">Comment</div>
            <div className="value">{detail.comment ?? "—"}</div>
          </div>
          <div className="meta-card">
            <div className="label">Categories</div>
            <div className="value">
              {detail.category_ids.length > 0 ? detail.category_ids.join(", ") : "—"}
            </div>
          </div>
        </div>
        <div className="explorer-metrics" aria-label="선택 테이블 메타데이터 건수">
          <div><strong>{columns.length}</strong><span>Columns</span></div>
          <div><strong>{outbound.length}</strong><span>Outbound FK</span></div>
          <div><strong>{inbound.length}</strong><span>Inbound FK</span></div>
          <div><strong>{indexes.length}</strong><span>Indexes</span></div>
        </div>
      </section>

      <div className="table-detail-tabs" role="tablist" aria-label="테이블 상세 항목">
        {DETAIL_TABS.map((item) => (
          <button key={item.id} type="button" role="tab"
            aria-selected={tab === item.id}
            className={tab === item.id ? "table-detail-tab selected" : "table-detail-tab"}
            onClick={() => setTab(item.id)}>
            {item.label}
            <span className="table-detail-tab-count">
              {item.id === "columns" ? columns.length : item.id === "relations" ? relations.length
                : item.id === "indexes" ? indexes.length : tableCategories.length}
            </span>
          </button>
        ))}
      </div>

      {tab === "columns" ? <section className="section" aria-label="Columns">
        <h3>Columns ({columns.length})</h3>
        <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Column</th>
              <th>Type</th>
              <th>Nullable</th>
              <th>Flags</th>
              <th>Default</th>
              <th>Comment</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((column) => (
              <tr key={`${column.schema_name ?? ""}.${column.table_name}.${column.name}`}>
                <td className="mono">{column.ordinal ?? "—"}</td>
                <td className="mono">{column.name}</td>
                <td className="mono">{column.data_type ?? "—"}</td>
                <td>{column.nullable == null ? "—" : column.nullable ? "YES" : "NO"}</td>
                <td>
                  <div className="chip-row">
                    {column.is_primary_key ? <span className="badge badge-pk">PK</span> : null}
                    {column.is_unique ? <span className="badge badge-unique">Unique</span> : null}
                  </div>
                </td>
                <td className="mono">{column.default ?? "—"}</td>
                <td>{column.comment ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      </section> : null}

      {tab === "relations" ? <section className="section" aria-label="Relationships">
        <h3>Relationships ({relations.length})</h3>
        <h4>Outbound FK ({outbound.length})</h4>
        {relationTable(outbound, "OUT")}
        <h4>Inbound FK ({inbound.length})</h4>
        {relationTable(inbound, "IN")}
      </section> : null}

      {tab === "indexes" ? <section className="section" aria-label="Indexes">
        <h3>Indexes ({indexes.length})</h3>
        {indexes.length === 0 ? (
          <div className="placeholder">No indexes for this table.</div>
        ) : (
          <div className="table-scroll"><table className="data-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Unique</th>
                <th>Method</th>
                <th>Columns</th>
              </tr>
            </thead>
            <tbody>
              {indexes.map((index) => (
                <tr key={`${index.schema_name ?? ""}.${index.name}`}>
                  <td className="mono">{index.name}</td>
                  <td>{index.unique == null ? "—" : String(index.unique)}</td>
                  <td className="mono">{index.method ?? "—"}</td>
                  <td className="mono">{index.columns.join(", ") || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </section> : null}

      {tab === "categories" ? <section className="section" aria-label="Table categories">
        <h3>Categories ({tableCategories.length})</h3>
        {tableCategories.length === 0 ? <p className="placeholder">지정된 Category가 없습니다.</p> : (
          <div className="table-scroll"><table className="data-table">
            <thead><tr><th>Category</th><th>Key</th><th>Primary</th><th>Source</th><th>Confidence</th><th>Note</th></tr></thead>
            <tbody>{tableCategories.flatMap((category) => {
              const assignments = category.assignments.filter((assignment) =>
                assignment.table_name === detail.name &&
                assignment.schema_name === detail.schema_name,
              );
              return (assignments.length ? assignments : [null]).map((assignment, index) => (
                <tr key={`${category.id}:${index}`}>
                  <td>{category.name ?? category.id}</td>
                  <td className="mono">{category.id}</td>
                  <td>{assignment?.is_primary == null ? "—" : assignment.is_primary ? "YES" : "NO"}</td>
                  <td>{assignment?.provenance ?? "—"}</td>
                  <td>{assignment?.confidence ?? "—"}</td>
                  <td>{assignment?.note ?? "—"}</td>
                </tr>
              ));
            })}</tbody>
          </table></div>
        )}
      </section> : null}

      <details className="table-technical-info">
        <summary>기술 정보</summary>
        <div>Table Type: {detail.table_type ?? "—"}</div>
        <div>Category Keys: {detail.category_ids.join(", ") || "—"}</div>
      </details>
    </div>
  );
}

interface CategoriesProps {
  categories: CatalogCategoryItem[];
  state: LoadState;
}

export function CategoriesPanel({ categories, state }: CategoriesProps) {
  return (
    <section className="categories-panel" aria-label="Categories">
      <h3>Categories</h3>
      {state.status === "loading" || state.status === "error" || state.status === "empty" ? (
        <StatusBanner state={state} emptyLabel="No categories in this Catalog" />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Description</th>
              <th>Assignments</th>
            </tr>
          </thead>
          <tbody>
            {categories.map((category) => (
              <tr key={category.id}>
                <td className="mono">{category.id}</td>
                <td>{category.name ?? "—"}</td>
                <td>{category.description ?? "—"}</td>
                <td className="mono">
                  {category.assignments.length === 0
                    ? "—"
                    : category.assignments
                        .map((a) =>
                          [a.schema_name, a.table_name].filter(Boolean).join("."),
                        )
                        .join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
