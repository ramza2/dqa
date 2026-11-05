import { useEffect, useMemo, useState } from "react";
import { loadActiveCatalogErd, type CatalogErdSnapshot } from "../api/catalogErd";
import {
  buildCatalogGraph,
  selectErdGraph,
  tableIdentity,
  type ErdHops,
  type ErdMode,
} from "../utils/catalogErd";
import { ActiveCatalogHeader, SourceSelector } from "./ActiveCatalogHeader";
import { useCatalogSource, useOptionalCatalogSource } from "../hooks/catalogSourceContext";
import { useOptionalErdFocus } from "../hooks/erdFocusContext";
import { CatalogSourceProvider } from "./CatalogSourceContext";
import { CatalogErdCanvas } from "./CatalogErdCanvas";
import { StatusBanner } from "./StatusBanner";
import "./ActiveCatalogErdExplorer.css";

type Loading = "idle" | "loading" | "ready" | "empty" | "error";

function ActiveCatalogErdExplorerBody({ sharedSourceBar = false }: { sharedSourceBar?: boolean }) {
  const {
    sources,
    selectedSource: source,
    selectSource,
    sourcesState,
  } = useCatalogSource();
  const erdFocus = useOptionalErdFocus();
  const [snapshot, setSnapshot] = useState<CatalogErdSnapshot | null>(null);
  const [status, setStatus] = useState<Loading>("idle");
  const [reload, setReload] = useState(0);
  const [mode, setMode] = useState<ErdMode>("full");
  const [focus, setFocus] = useState("");
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [hops, setHops] = useState<ErdHops>(1);
  const [selectedTable, setSelectedTable] = useState("");
  const [selectedLink, setSelectedLink] = useState("");

  useEffect(() => {
    if (sourcesState.status !== "ready" || !source) {
      setSnapshot(null);
      setStatus("idle");
      return;
    }
    let valid = true;
    setSnapshot(null);
    setStatus("loading");
    setFocus("");
    setSelectedTable("");
    setSelectedLink("");
    setCategory("");
    setSearch("");
    setMode("full");
    setHops(1);
    loadActiveCatalogErd(source).then((result) => {
      if (!valid) return;
      setSnapshot(result);
      setStatus(result.tables.length ? "ready" : "empty");
    }).catch(() => { if (valid) setStatus("error"); });
    return () => { valid = false; };
  }, [source, reload, sourcesState.status]);

  const graph = useMemo(() => snapshot
    ? buildCatalogGraph(snapshot.tables, snapshot.relations)
    : { nodes: [], links: [], unresolved: 0 }, [snapshot]);
  const selection = useMemo(() => selectErdGraph(graph, {
    mode, focus, category, search, hops,
  }), [graph, mode, focus, category, search, hops]);
  const categoryNames = useMemo(() => Object.fromEntries(
    snapshot?.categories.map((item) => [item.id, item.name ?? item.id]) ?? [],
  ), [snapshot]);
  // SourceSelector updates before the async effect can clear the previous response.
  // Never render an earlier source's Catalog even for one intermediate frame.
  const visibleSnapshot = snapshot?.active.source_name === source ? snapshot : null;
  const selectedNode = selection.nodes.find((node) => node.id === selectedTable)
    ?? graph.nodes.find((node) => node.id === selectedTable);
  const selectedRelation = selection.links.find((link) => link.id === selectedLink)
    ?? graph.links.find((link) => link.id === selectedLink);
  const tableLabel = (id: string) => {
    const node = graph.nodes.find((item) => item.id === id);
    return node ? `${node.schema}.${node.name}` : "확인되지 않은 테이블";
  };

  // Consume one-shot Table Explorer → ERD focus after the active Catalog load succeeds.
  useEffect(() => {
    const request = erdFocus?.focusRequest;
    if (!request || status !== "ready" || !visibleSnapshot) {
      return;
    }
    if (request.sourceName !== source) {
      erdFocus.clearErdFocus();
      return;
    }
    const id = tableIdentity(request.schemaName, request.tableName);
    if (!graph.nodes.some((node) => node.id === id)) {
      erdFocus.clearErdFocus();
      return;
    }
    setMode("neighborhood");
    setFocus(id);
    setSelectedTable(id);
    setSelectedLink("");
    setSearch("");
    setCategory("");
    setHops(request.hops);
    erdFocus.clearErdFocus();
  }, [erdFocus, status, visibleSnapshot, source, graph.nodes]);

  const incidentLinks = selectedNode
    ? graph.links.filter((item) => item.source === selectedNode.id || item.target === selectedNode.id)
    : [];

  return <div className="dqa-erd-page" data-testid="active-catalog-erd-explorer">
    <header className="app-header">
      <div className="app-title-row">
        <h1>ERD Explorer</h1>
        <span className="subtitle">React Flow + ELK 기반 활성 Catalog 테이블 관계도</span>
      </div>
      {!sharedSourceBar ? <SourceSelector
        sources={sources}
        selectedSource={source}
        onSelect={selectSource}
        disabled={sourcesState.status === "loading"}
        emptyLabel="선택 가능한 활성 Catalog Source가 없습니다"
      /> : null}
      {visibleSnapshot ? <ActiveCatalogHeader active={visibleSnapshot.active} staleWarning={null} hideSource={sharedSourceBar} /> : null}
    </header>

    {sourcesState.status === "loading" ? <p className="dqa-erd-notice" role="status">활성 Catalog 목록 확인 중…</p> : null}
    {sourcesState.status === "empty" ? (
      <p className="dqa-erd-notice">활성 Catalog가 없습니다. 검증된 Package를 먼저 활성화해야 합니다.</p>
    ) : null}
    {sourcesState.status === "error" ? <StatusBanner state={sourcesState} /> : null}
    {sourcesState.status === "ready" && source && status === "loading" ? (
      <p className="dqa-erd-notice" role="status">Source·Revision·Fingerprint를 검증하며 ERD 메타데이터를 조회 중…</p>
    ) : null}
    {sourcesState.status === "ready" && source && status === "error" ? (
      <div className="dqa-erd-notice banner banner-error" role="alert">
        ERD 조회 또는 Catalog 버전 정합성 검증에 실패했습니다.
        <button type="button" className="dqa-erd-retry" onClick={() => setReload((value) => value + 1)}>다시 조회</button>
      </div>
    ) : null}
    {sourcesState.status === "ready" && source && status === "empty" ? (
      <p className="dqa-erd-notice">활성 Catalog에 테이블이 없습니다.</p>
    ) : null}

    {status === "ready" && visibleSnapshot ? <main className="dqa-erd-content">
      <p className="dqa-erd-security-note">
        이 화면은 활성 Catalog의 메타데이터만 표시합니다. 실제 DEMIS 연결·조회 권한 또는
        미승인 Inspector Snapshot의 승인 상태를 뜻하지 않습니다.
      </p>
      <div className="dqa-erd-metrics" aria-label="ERD 메타데이터 건수">
        <div><strong>{visibleSnapshot.totalTables}</strong><span>Catalog Tables</span></div>
        <div><strong>{visibleSnapshot.totalRelations}</strong><span>Catalog FK Relations</span></div>
        <div><strong>{visibleSnapshot.totalCategories}</strong><span>Categories</span></div>
        <div><strong>{selection.nodes.length}</strong><span>화면 표시 Tables</span></div>
      </div>
      {visibleSnapshot.truncated || graph.unresolved || selection.hiddenNodes || selection.hiddenLinks ? (
        <div className="banner banner-warn" role="status">
          {visibleSnapshot.truncated ? "대규모 Catalog: 최초 Table 1,000건 / FK 2,000건 / Category 500건까지만 읽었습니다. 관계도가 불완전할 수 있습니다. " : null}
          {graph.unresolved ? `현재 불러온 Table로 연결할 수 없는 FK ${graph.unresolved}건은 생략했습니다. ` : null}
          {selection.hiddenNodes ? `배치 성능을 위해 일치 Table ${selection.hiddenNodes}건을 추가 생략했습니다. ` : null}
          {selection.hiddenLinks ? `관계선 ${selection.hiddenLinks}건을 추가 생략했습니다.` : null}
        </div>
      ) : null}
      <div className="dqa-erd-filters">
        <label>View
          <select aria-label="ERD 보기 방식" value={mode} onChange={(event) => {
            setMode(event.target.value as ErdMode); setSelectedLink("");
          }}>
            <option value="full">전체 ERD</option>
            <option value="neighborhood">선택 Table 주변</option>
            <option value="category">Category ERD</option>
          </select>
        </label>
        {mode === "neighborhood" ? <label>Focus Table
          <select aria-label="ERD 중심 테이블" value={focus} onChange={(event) => {
            setFocus(event.target.value);
            setSelectedTable(event.target.value);
            setSelectedLink("");
          }}>
            <option value="">테이블 선택</option>
            {graph.nodes.map((node) => <option key={node.id} value={node.id}>
              {node.schema}.{node.name} — {node.comment ?? "설명 없음"}
            </option>)}
          </select>
        </label> : null}
        {mode === "neighborhood" ? <label>탐색 범위
          <select aria-label="ERD 관계 단계" value={hops}
            onChange={(event) => setHops(Number(event.target.value) as ErdHops)}>
            <option value={1}>1단계 FK</option>
            <option value={2}>2단계 FK</option>
            <option value={3}>3단계 FK</option>
          </select>
        </label> : null}
        {mode === "category" ? <label>Category
          <select aria-label="ERD Category" value={category} onChange={(event) => setCategory(event.target.value)}>
            <option value="">Category 선택</option>
            {visibleSnapshot.categories.map((item) => <option key={item.id} value={item.id}>
              {item.name ?? item.id}
            </option>)}
          </select>
        </label> : null}
        <label>Table / Comment 검색
          <input aria-label="ERD 테이블 검색" value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="예: TB_PATIENT, 진료" maxLength={128} />
        </label>
      </div>

      <div className="dqa-erd-workspace">
        <div className="dqa-erd-graph-pane">
          {selection.nodes.length > 0 ? <CatalogErdCanvas
            tables={selection.nodes} links={selection.links} distances={selection.distances}
            focus={mode === "neighborhood" ? focus : ""}
            categoryNames={categoryNames}
            selectedTable={selectedTable} selectedLink={selectedLink}
            onTableSelect={(id) => { setSelectedTable(id); setSelectedLink(""); }}
            onLinkSelect={setSelectedLink}
          /> : <p className="dqa-erd-notice">
            {mode === "neighborhood" && !focus ? "중심 테이블을 선택하세요." :
              mode === "category" && !category ? "Category를 선택하세요." :
                "조건에 맞는 Table이 없습니다."}
          </p>}
        </div>

        <section className="dqa-erd-inspector" aria-label="ERD 관계 상세" data-testid="erd-relation-inspector">
          <h3>관계 상세</h3>
          {selectedRelation ? <div data-testid="erd-relation-detail">
            <div className="dqa-erd-detail-badge">FK 관계</div>
            <strong>{selectedRelation.name ?? "이름 없는 FK"}</strong>
            <p className="dqa-erd-detail-path">
              <span className="mono">{tableLabel(selectedRelation.source)}</span>
              <span aria-hidden="true"> → </span>
              <span className="mono">{tableLabel(selectedRelation.target)}</span>
            </p>
            <h4>컬럼 매핑</h4>
            {selectedRelation.mapping.length ? (
              <table className="dqa-erd-mapping-table">
                <thead>
                  <tr>
                    <th scope="col">Source column</th>
                    <th scope="col">Referenced column</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedRelation.mapping.map((item) => (
                    <tr key={`${item.source}->${item.target}`}>
                      <td className="mono">{item.source}</td>
                      <td className="mono">{item.target}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <p>컬럼 매핑 없음</p>}
            <div className="dqa-erd-detail-actions">
              <button type="button" className="dqa-erd-retry" onClick={() => {
                setFocus(selectedRelation.source);
                setSelectedTable(selectedRelation.source);
                setMode("neighborhood");
                setSearch("");
              }}>Source 테이블 중심</button>
              <button type="button" className="dqa-erd-retry" onClick={() => {
                setFocus(selectedRelation.target);
                setSelectedTable(selectedRelation.target);
                setMode("neighborhood");
                setSearch("");
              }}>Referenced 테이블 중심</button>
            </div>
          </div> : selectedNode ? <div data-testid="erd-table-detail">
            <div className="dqa-erd-detail-badge">Table</div>
            <strong className="mono">{selectedNode.schema}.{selectedNode.name}</strong>
            <p>{selectedNode.comment ?? "DB COMMENT 없음"}</p>
            <p>연결된 FK {incidentLinks.length}건
              {mode === "neighborhood" && focus === selectedNode.id
                ? ` · 현재 ${hops}단계 탐색 중심` : null}
            </p>
            <button type="button" className="dqa-erd-retry" onClick={() => {
              setFocus(selectedNode.id); setMode("neighborhood"); setSearch(""); setSelectedLink("");
            }}>이 테이블 중심 보기</button>
            <ul className="dqa-erd-link-list">{incidentLinks.map((item) => <li key={item.id}>
              <button type="button" className={`dqa-erd-link-button${item.id === selectedLink ? " selected" : ""}`}
                onClick={() => setSelectedLink(item.id)}>
                <span className="dqa-erd-link-name">{item.name ?? "FK"}</span>
                <span className="mono dqa-erd-link-map">{item.mapping.map((pair) =>
                  `${pair.source} → ${pair.target}`).join(", ") || "컬럼 매핑 없음"}</span>
              </button>
            </li>)}</ul>
          </div> : <p>그래프의 테이블 또는 FK 관계선을 선택하면 컬럼 매핑과 관계를 확인할 수 있습니다.</p>}
        </section>
      </div>
      <p className="dqa-erd-footnote">React Flow 그래프는 읽기 전용이며 테이블/관계선을 수정하지 않습니다. Source 또는 Revision이 변경되면 새로 조회합니다.</p>
    </main> : null}
  </div>;
}

export function ActiveCatalogErdExplorer({ sharedSourceBar = false }: { sharedSourceBar?: boolean }) {
  const shared = useOptionalCatalogSource();
  if (!shared) {
    return (
      <CatalogSourceProvider>
        <ActiveCatalogErdExplorerBody sharedSourceBar={sharedSourceBar} />
      </CatalogSourceProvider>
    );
  }
  return <ActiveCatalogErdExplorerBody sharedSourceBar={sharedSourceBar} />;
}
