import { useEffect, useRef, useState } from "react";
import { listColumns, listTables } from "../api/catalog";
import { previewCatalogQuery } from "../api/queryBuilder";
import type { CatalogActiveSummary, CatalogColumnItem, CatalogTableItem } from "../types/catalog";
import type { CatalogPreviewOperator, CatalogPreviewPredicate, CatalogPreviewResponse } from "../types/queryBuilder";
import { formatAssistantError } from "../utils/queryAssistant";

const OPS: { value: CatalogPreviewOperator; label: string }[] = [
  { value: "EQ", label: "같음 (=)" }, { value: "NE", label: "다름 (<>)" },
  { value: "LT", label: "작음 (<)" }, { value: "LE", label: "이하 (<=)" },
  { value: "GT", label: "큼 (>)" }, { value: "GE", label: "이상 (>=)" },
  { value: "LIKE", label: "문자열 포함 형태 (LIKE)" },
  { value: "IS_NULL", label: "값 없음 (IS NULL)" },
  { value: "IS_NOT_NULL", label: "값 있음 (IS NOT NULL)" },
];

function tableKey(table: CatalogTableItem): string {
  return JSON.stringify([table.schema_name, table.name]);
}

export function CatalogGraphicalBuilder({
  active,
}: {
  active: CatalogActiveSummary | undefined;
}) {
  const sequence = useRef(0);
  const mounted = useRef(true);
  const [tableQuery, setTableQuery] = useState("");
  const [tables, setTables] = useState<CatalogTableItem[]>([]);
  const [tableTotal, setTableTotal] = useState(0);
  const [tableState, setTableState] = useState<"idle" | "loading">("idle");
  const [tableError, setTableError] = useState<string | null>(null);
  const [selectedTable, setSelectedTable] = useState("");
  const [columns, setColumns] = useState<CatalogColumnItem[]>([]);
  const [columnState, setColumnState] = useState<"idle" | "loading">("idle");
  const [columnError, setColumnError] = useState<string | null>(null);
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [predicates, setPredicates] = useState<CatalogPreviewPredicate[]>([]);
  const [rowLimit, setRowLimit] = useState(50);
  const [preview, setPreview] = useState<CatalogPreviewResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      sequence.current += 1;
    };
  }, []);

  const source = active?.source_name ?? "";
  const selected = tables.find((t) => tableKey(t) === selectedTable);
  const clearPreview = () => {
    sequence.current += 1;
    setPreview(null);
    setPreviewError(null);
    setPreviewBusy(false);
  };
  const identityMatches = (r: { source_name: string; revision_id?: number; catalog_revision_id?: number; schema_fingerprint: string }) =>
    r.source_name === active?.source_name &&
    (r.revision_id ?? r.catalog_revision_id) === active?.revision_id &&
    r.schema_fingerprint === active?.schema_fingerprint;

  const fetchTables = async () => {
    if (!active || tableState === "loading") return;
    clearPreview();
    const seq = sequence.current;
    setTables([]);
    setTableTotal(0);
    setSelectedTable("");
    setColumns([]);
    setSelectedColumns([]);
    setPredicates([]);
    setColumnError(null);
    setTableError(null);
    setTableState("loading");
    try {
      const result = await listTables(source, { q: tableQuery.trim() || undefined, limit: 500, offset: 0 });
      if (!mounted.current || seq !== sequence.current) return;
      if (!identityMatches(result)) throw new Error("CATALOG_MISMATCH");
      setTables(result.items);
      setTableTotal(result.total);
    } catch (error) {
      if (!mounted.current || seq !== sequence.current) return;
      setTableError(error instanceof Error && error.message === "CATALOG_MISMATCH"
        ? "Catalog가 변경되었습니다. 목록을 다시 불러오세요."
        : formatAssistantError(error).message);
    } finally {
      if (mounted.current && seq === sequence.current) setTableState("idle");
    }
  };

  const chooseTable = async (value: string) => {
    clearPreview();
    const seq = sequence.current;
    setSelectedTable(value);
    setColumns([]);
    setSelectedColumns([]);
    setPredicates([]);
    setColumnError(null);
    const target = tables.find((t) => tableKey(t) === value);
    if (!target || !active) return;
    setColumnState("loading");
    try {
      const result = await listColumns(source, {
        schema_name: target.schema_name, table_name: target.name, limit: 500, offset: 0,
      });
      if (!mounted.current || seq !== sequence.current) return;
      if (!identityMatches(result)) throw new Error("CATALOG_MISMATCH");
      if (result.total > result.items.length) {
        throw new Error("COLUMN_LIMIT");
      }
      setColumns(result.items.filter((col) => col.schema_name === target.schema_name && col.table_name === target.name));
    } catch (error) {
      if (!mounted.current || seq !== sequence.current) return;
      setColumnError(error instanceof Error && error.message === "CATALOG_MISMATCH"
        ? "Catalog가 변경되었습니다. 테이블을 다시 선택하세요."
        : error instanceof Error && error.message === "COLUMN_LIMIT"
          ? "컬럼 수가 화면 조회 한도를 초과했습니다."
          : formatAssistantError(error).message);
    } finally {
      if (mounted.current && seq === sequence.current) setColumnState("idle");
    }
  };

  const toggleColumn = (name: string, checked: boolean) => {
    clearPreview();
    setSelectedColumns((current) => checked
      ? current.length < 16 && !current.includes(name) ? [...current, name] : current
      : current.filter((item) => item !== name));
  };

  const runPreview = async () => {
    if (!active || !selected || selectedColumns.length === 0 || previewBusy) return;
    clearPreview();
    const seq = sequence.current;
    setPreviewBusy(true);
    try {
      const result = await previewCatalogQuery({
        source_name: source,
        catalog_revision_id: active.revision_id,
        schema_fingerprint: active.schema_fingerprint,
        schema_name: selected.schema_name,
        table_name: selected.name,
        columns: selectedColumns,
        predicates,
        row_limit: rowLimit,
      });
      if (!mounted.current || seq !== sequence.current) return;
      if (!identityMatches(result) || !result.preview_only || result.executable !== false ||
          result.approved !== false || result.template_id !== null) {
        throw new Error("PREVIEW_IDENTITY_MISMATCH");
      }
      setPreview(result);
    } catch (error) {
      if (!mounted.current || seq !== sequence.current) return;
      setPreviewError(error instanceof Error && error.message === "PREVIEW_IDENTITY_MISMATCH"
        ? "미리보기 검증 결과가 현재 Catalog와 일치하지 않습니다."
        : formatAssistantError(error).message);
    } finally {
      if (mounted.current && seq === sequence.current) setPreviewBusy(false);
    }
  };

  return (
    <section className="qa-panel" aria-labelledby="catalog-builder-heading" data-testid="catalog-graphical-builder">
      <h2 id="catalog-builder-heading">그래픽 조회 조건 작성 (SQL 미리보기 전용)</h2>
      <p className="muted">
        활성 Catalog의 단일 테이블·컬럼·조건으로 SELECT 형태만 확인합니다.
        조건값은 입력·전송하지 않으며 바인드 자리표시자만 만듭니다.
        이 SQL로는 조회를 실행하거나 승인 템플릿을 생성할 수 없습니다.
      </p>
      <label className="param-field">
        <span className="param-label">테이블 검색어 (이름·설명)</span>
        <input aria-label="테이블 검색어" value={tableQuery} maxLength={100}
          disabled={!active || tableState === "loading"}
          onChange={(event) => {
            clearPreview();
            setTableQuery(event.target.value);
            setTables([]);
            setTableTotal(0);
            setSelectedTable("");
            setColumns([]);
            setSelectedColumns([]);
            setPredicates([]);
          }} />
      </label>
      <div className="qa-actions">
        <button type="button" onClick={() => void fetchTables()}
          disabled={!active || tableState === "loading"}>
          {tableState === "loading" ? "테이블 불러오는 중…" : "테이블 목록 불러오기"}
        </button>
      </div>
      {tableError ? <div className="banner banner-error" role="alert">{tableError}</div> : null}
      {tableTotal > tables.length ? (
        <p className="muted">테이블 {tableTotal}개 중 첫 {tables.length}개만 표시합니다.</p>
      ) : null}
      {tables.length > 0 ? (
        <label className="param-field">
          <span className="param-label">조회 테이블</span>
          <select aria-label="조회 테이블" value={selectedTable}
            onChange={(event) => void chooseTable(event.target.value)}>
            <option value="">테이블 선택</option>
            {tables.map((t) => (
              <option key={tableKey(t)} value={tableKey(t)}>
                {t.schema_name}.{t.name}{t.comment ? ` — ${t.comment}` : ""}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {columnState === "loading" ? <p className="muted">컬럼 불러오는 중…</p> : null}
      {columnError ? <div className="banner banner-error" role="alert">{columnError}</div> : null}
      {columns.length > 0 ? (
        <>
          <fieldset className="qb-column-set">
            <legend>표시할 컬럼 (최대 16개)</legend>
            {columns.map((col) => (
              <label key={col.name} className="qb-column-check">
                <input type="checkbox" aria-label={`컬럼 ${col.name}`}
                  checked={selectedColumns.includes(col.name)}
                  disabled={!selectedColumns.includes(col.name) && selectedColumns.length >= 16}
                  onChange={(event) => toggleColumn(col.name, event.target.checked)} />
                <span>{col.name}{col.comment ? ` — ${col.comment}` : ""}</span>
              </label>
            ))}
          </fieldset>
          <div className="qa-actions">
            <strong>조건 (최대 4개)</strong>
            <button type="button" disabled={predicates.length >= 4}
              onClick={() => {
                clearPreview();
                setPredicates((items) => [...items, { column: columns[0].name, operator: "EQ" }]);
              }}>조건 추가</button>
          </div>
          {predicates.map((pred, idx) => (
            <div className="qa-actions qb-predicate" key={idx}>
              <label>
                <span className="param-label">조건 컬럼 {idx + 1}</span>
                <select aria-label={`조건 컬럼 ${idx + 1}`} value={pred.column}
                  onChange={(event) => {
                    clearPreview();
                    setPredicates((items) => items.map((p, i) => i === idx ? { ...p, column: event.target.value } : p));
                  }}>
                  {columns.map((col) => <option key={col.name} value={col.name}>{col.name}</option>)}
                </select>
              </label>
              <label>
                <span className="param-label">조건 연산자 {idx + 1}</span>
                <select aria-label={`조건 연산자 ${idx + 1}`} value={pred.operator}
                  onChange={(event) => {
                    clearPreview();
                    setPredicates((items) => items.map((p, i) => i === idx ? { ...p, operator: event.target.value as CatalogPreviewOperator } : p));
                  }}>
                  {OPS.map((op) => <option key={op.value} value={op.value}>{op.label}</option>)}
                </select>
              </label>
              <button type="button" aria-label={`조건 제거 ${idx + 1}`} onClick={() => {
                clearPreview();
                setPredicates((items) => items.filter((_, i) => i !== idx));
              }}>제거</button>
            </div>
          ))}
          <label className="param-field">
            <span className="param-label">행 수 상한 (최대 100)</span>
            <input aria-label="미리보기 행 수 상한" type="number" min={1} max={100} step={1}
              value={rowLimit} onChange={(event) => {
                clearPreview();
                setRowLimit(Number(event.target.value));
              }} />
          </label>
          <div className="qa-actions">
            <button type="button" onClick={() => void runPreview()}
              disabled={selectedColumns.length === 0 || !Number.isInteger(rowLimit) ||
                rowLimit < 1 || rowLimit > 100 || previewBusy || columnState === "loading"}>
              {previewBusy ? "SQL 검증 중…" : "SQL 미리보기 생성"}
            </button>
          </div>
          {previewError ? <div className="banner banner-error" role="alert">{previewError}</div> : null}
          {preview ? (
            <div data-testid="catalog-sql-preview" className="qa-preview-summary">
              <strong>실행 불가 · 미승인 SQL 예시</strong>
              <pre className="qb-sql">{preview.sql_text}</pre>
              <p className="muted">바인드 변수: {preview.parameters.map((p) => `:${p.name} (${p.type})`).join(", ")}</p>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
