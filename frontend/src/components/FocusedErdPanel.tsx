import type { CatalogTableDetail, DirectedRelation } from "../types/catalog";
import { formatColumnMapping } from "../utils/relations";
import { buildFocusedErd, type FocusedErdEdge } from "../utils/focusedErd";

interface Props {
  detail: CatalogTableDetail;
  relations: DirectedRelation[];
  source: string;
  revision: number;
}

function RelationCard({ relation }: { relation: FocusedErdEdge }) {
  return (
    <li className="erd-edge">
      <div className="erd-edge-title">
        <span className="mono">{relation.neighborSchema}.{relation.neighborTable}</span>
        {relation.outsideSchema ? (
          <span className="badge badge-warn">외부 스키마 참조 (권한 미확인)</span>
        ) : null}
      </div>
      <div className="erd-edge-meta">
        {relation.name ?? "이름 없는 FK"} · {relation.direction === "IN" ? "들어오는 참조" : "나가는 참조"}
      </div>
      <div className="erd-edge-meta mono">{formatColumnMapping(relation.columns)}</div>
    </li>
  );
}

export function FocusedErdPanel({ detail, relations, source, revision }: Props) {
  const graph = buildFocusedErd(detail.schema_name, detail.name, relations);
  return (
    <section className="section focused-erd" aria-label="테이블 관계 ERD">
      <h3>테이블 관계 ERD (1단계)</h3>
      <p className="muted">
        Source: {source} · Revision: {revision} · FK 관계 {graph.total}건
      </p>
      <p className="muted">
        기존 활성 Catalog에서 확인된 관계 메타데이터만 표시합니다.
        실제 DEMIS 접속, 외부 테이블 조회 권한 또는 업무 의미를 검증하지 않습니다.
      </p>
      {graph.hidden > 0 || graph.unknown > 0 ? (
        <p role="status" className="banner banner-warn">
          최대 40건 표시. 생략 {graph.hidden}건, 대상 스키마 확인 불가 {graph.unknown}건.
          전체 스키마 관계가 완전하다는 의미가 아닙니다.
        </p>
      ) : null}
      <div className="erd-layout">
        <div className="erd-side">
          <h4>이 테이블을 참조 ({graph.inbound.length})</h4>
          <ul className="erd-list">
            {graph.inbound.length
              ? graph.inbound.map(item => <RelationCard key={item.key} relation={item} />)
              : <li className="erd-empty">들어오는 FK 없음</li>}
          </ul>
          <span className="erd-arrow">→ 중심 테이블</span>
        </div>
        <div className="erd-center" aria-label="중심 테이블">
          <span className="muted">선택한 테이블</span>
          <strong className="mono">{detail.schema_name}.{detail.name}</strong>
          <span>{detail.comment ?? "설명 없음"}</span>
        </div>
        <div className="erd-side">
          <h4>이 테이블이 참조 ({graph.outbound.length})</h4>
          <span className="erd-arrow">중심 테이블 →</span>
          <ul className="erd-list">
            {graph.outbound.length
              ? graph.outbound.map(item => <RelationCard key={item.key} relation={item} />)
              : <li className="erd-empty">나가는 FK 없음</li>}
          </ul>
        </div>
      </div>
      <p className="muted">
        현재 선택된 테이블의 1단계 FK만 표시합니다. API 페이지 제한에 따라
        전체 관계가 아닐 수 있으며 전체 ERD와 DOCX 분석서는 후속 단계입니다.
      </p>
    </section>
  );
}
