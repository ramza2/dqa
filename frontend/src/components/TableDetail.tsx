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
  state: LoadState;
}

export function TableDetailPanel({
  detail,
  columns,
  relations,
  indexes,
  state,
}: DetailProps) {
  if (state.status === "idle") {
    return <div className="placeholder">Select a table to inspect metadata.</div>;
  }
  if (state.status === "loading" || state.status === "error") {
    return <StatusBanner state={state} />;
  }
  if (!detail) {
    return <div className="placeholder">No table detail available.</div>;
  }

  return (
    <div>
      <section className="section" aria-label="Table overview">
        <h3>Overview</h3>
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
      </section>

      <section className="section" aria-label="Columns">
        <h3>Columns ({columns.length})</h3>
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
      </section>

      <section className="section" aria-label="Relationships">
        <h3>Relationships ({relations.length})</h3>
        {relations.length === 0 ? (
          <div className="placeholder">No relationships for this table.</div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Direction</th>
                <th>Constraint</th>
                <th>Source</th>
                <th>Target</th>
                <th>Column mapping</th>
              </tr>
            </thead>
            <tbody>
              {relations.map((relation) => (
                <tr key={relation.key}>
                  <td>
                    <span className="badge badge-muted">{relation.direction}</span>
                  </td>
                  <td className="mono">{relation.name ?? "—"}</td>
                  <td className="mono">
                    {[relation.sourceSchema, relation.sourceTable].filter(Boolean).join(".")}
                  </td>
                  <td className="mono">
                    {[relation.targetSchema, relation.targetTable].filter(Boolean).join(".")}
                  </td>
                  <td className="mono">{formatColumnMapping(relation.columns)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="section" aria-label="Indexes">
        <h3>Indexes ({indexes.length})</h3>
        {indexes.length === 0 ? (
          <div className="placeholder">No indexes for this table.</div>
        ) : (
          <table className="data-table">
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
          </table>
        )}
      </section>
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
