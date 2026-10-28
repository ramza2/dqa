import { useEffect, useRef, useState } from "react";
import {
  getReviewTemplate, getReviewTemplateSqlSafety, listReviewTemplates,
} from "../api/templateReview";
import type {
  ReviewTemplateDetail, ReviewTemplateList, ReviewTemplateSummary,
  TemplateSqlSafetyReview,
} from "../types/templateReview";
import { formatAssistantError } from "../utils/queryAssistant";
import { CatalogApiError } from "../types/catalog";

const PAGE_SIZE = 50;

// Query Assistant's shared formatter describes QUERY_OPERATE rights, while
// this read-only portal requires TEMPLATE_READ. Keep the 403 denial unchanged.
function reviewErrorMessage(error: unknown): string {
  if (error instanceof CatalogApiError && error.status === 403 &&
      error.code === "AUTHORIZATION_DENIED") {
    return "템플릿 검토 현황 열람 권한이 없습니다.";
  }
  return formatAssistantError(error).message;
}

function statusName(value: string | null): string {
  return ({
    DRAFT: "초안", IN_REVIEW: "검토 중",
    APPROVED: "승인됨", REJECTED: "반려됨",
  } as Record<string, string>)[value ?? ""] ?? "상태 미지정";
}

export function TemplateReviewPortal() {
  const sequence = useRef(0);
  const detailSequence = useRef(0);
  const mounted = useRef(false);
  const [sourceName, setSourceName] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [page, setPage] = useState<ReviewTemplateList | null>(null);
  const [listBusy, setListBusy] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<ReviewTemplateDetail | null>(null);
  const [safety, setSafety] = useState<TemplateSqlSafetyReview | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const visibleItems = page?.items.filter((item) =>
    statusFilter === "ALL" || item.approval_status === statusFilter) ?? [];

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      sequence.current++;
      detailSequence.current++;
    };
  }, []);

  const clearDetail = () => {
    detailSequence.current++;
    setSelected(null);
    setDetail(null);
    setSafety(null);
    setDetailError(null);
    setDetailBusy(false);
  };

  const clearList = () => {
    sequence.current++;
    clearDetail();
    setPage(null);
    setListError(null);
    setListBusy(false);
  };

  const loadList = async (offset = 0) => {
    const seq = ++sequence.current;
    clearDetail();
    setPage(null);
    setListError(null);
    setListBusy(true);
    try {
      const result = await listReviewTemplates(sourceName, offset);
      if (!mounted.current || seq !== sequence.current) return;
      // Do not trust a partial/oversized page or cross-page result from a
      // stale API response. No SQL should be rendered until version validation.
      if (result.limit !== PAGE_SIZE || result.offset !== offset ||
          !Array.isArray(result.items) || result.items.length > PAGE_SIZE ||
          result.items.some((item) =>
            (sourceName.trim() !== "" && item.source_name !== sourceName.trim()) ||
            !Number.isSafeInteger(item.id) || item.id <= 0)) {
        setListError("템플릿 목록 응답이 요청 범위와 일치하지 않습니다.");
        return;
      }
      setPage(result);
    } catch (error) {
      if (mounted.current && seq === sequence.current) {
        setListError(reviewErrorMessage(error));
      }
    } finally {
      if (mounted.current && seq === sequence.current) setListBusy(false);
    }
  };

  const chooseTemplate = async (item: ReviewTemplateSummary) => {
    const seq = ++detailSequence.current;
    setSelected(item.id);
    setDetail(null);
    setSafety(null);
    setDetailError(null);
    setDetailBusy(true);
    try {
      const [nextDetail, nextSafety] = await Promise.all([
        getReviewTemplate(item.id), getReviewTemplateSqlSafety(item.id),
      ]);
      if (!mounted.current || seq !== detailSequence.current) return;
      // Both lookups may span a concurrent version change. Refuse any
      // cross-version/state mixing; force a new list/selection instead.
      if (nextDetail.id !== item.id || nextDetail.source_name !== item.source_name ||
          nextDetail.stable_key !== item.stable_key ||
          nextDetail.current_version_id !== item.current_version_id ||
          nextDetail.current_version !== item.current_version ||
          nextDetail.approval_status !== item.approval_status ||
          nextDetail.version.id !== nextDetail.current_version_id ||
          nextDetail.version.version !== nextDetail.current_version ||
          nextDetail.version.approval_status !== nextDetail.approval_status ||
          nextSafety.template_id !== nextDetail.id ||
          nextSafety.version_id !== nextDetail.version.id ||
          nextSafety.version !== nextDetail.version.version ||
          !nextDetail.compatibility ||
          nextDetail.compatibility.pinned_revision_id !== nextDetail.version.compatibility.pinned_revision_id ||
          nextDetail.compatibility.pinned_schema_fingerprint !== nextDetail.version.compatibility.pinned_schema_fingerprint) {
        setDetailError("버전·상태 또는 Catalog가 변경되었습니다. 목록을 새로고침하고 다시 선택하세요.");
        return;
      }
      setDetail(nextDetail);
      setSafety(nextSafety);
    } catch (error) {
      if (mounted.current && seq === detailSequence.current) {
        setDetailError(reviewErrorMessage(error));
      }
    } finally {
      if (mounted.current && seq === detailSequence.current) setDetailBusy(false);
    }
  };

  return (
    <main className="workflow-home" data-testid="template-review-portal">
      <header className="workflow-hero">
        <h1>Query Template 검토 현황</h1>
        <p>기존 템플릿의 승인 상태, Catalog 호환성, SQL 안전성 결과를 읽기 전용으로 확인합니다.</p>
        <p className="workflow-notice">
          <strong>조회 전용</strong> — 이 화면에서 생성·수정·검토 제출·승인·반려·활성화·실행하지 않습니다.
          SQL 안전성 통과는 실행 승인이나 실제 DEMIS 접속 허가를 의미하지 않습니다.
        </p>
      </header>
      <section className="qa-panel" aria-labelledby="review-list-heading">
        <h2 id="review-list-heading">템플릿 목록</h2>
        <label className="param-field">
          <span className="param-label">Source 이름 (선택 입력)</span>
          <input aria-label="템플릿 Source 필터" maxLength={255} value={sourceName}
            onChange={(event) => {
              clearList();
              setSourceName(event.target.value);
            }} />
        </label>
        <label className="param-field">
          <span className="param-label">승인 상태 (현재 페이지 필터)</span>
          <select aria-label="템플릿 승인 상태 필터" value={statusFilter}
            onChange={(event) => { clearDetail(); setStatusFilter(event.target.value); }}>
            <option value="ALL">전체</option>
            <option value="DRAFT">초안</option>
            <option value="IN_REVIEW">검토 중</option>
            <option value="APPROVED">승인됨</option>
            <option value="REJECTED">반려됨</option>
          </select>
        </label>
        <div className="qa-actions">
          <button type="button" disabled={listBusy} onClick={() => void loadList()}>
            {listBusy ? "목록 불러오는 중…" : "템플릿 목록 조회"}
          </button>
        </div>
        {listError ? <div role="alert" className="banner banner-error">{listError}</div> : null}
        {page ? (
          <>
            <p className="muted">총 {page.total}개 · {page.items.length === 0
              ? "현재 페이지 비어 있음"
              : `${page.offset + 1}–${page.offset + page.items.length}개 표시`}
              {statusFilter !== "ALL" ? ` · 현재 페이지 필터 일치 ${visibleItems.length}개` : ""}
            </p>
            <div className="qa-actions">
              <button type="button" disabled={listBusy || page.offset === 0}
                onClick={() => void loadList(Math.max(0, page.offset - PAGE_SIZE))}>이전 페이지</button>
              <button type="button" disabled={listBusy || page.offset + page.items.length >= page.total}
                onClick={() => void loadList(page.offset + PAGE_SIZE)}>다음 페이지</button>
            </div>
            {visibleItems.length === 0 ? <p>현재 페이지에 해당 상태의 템플릿이 없습니다.</p> : (
              <ul className="qb-review-list">
                {visibleItems.map((item) => (
                  <li key={item.id}>
                    <button type="button" aria-label={`검토 대상 ${item.name}`}
                      disabled={detailBusy} onClick={() => void chooseTemplate(item)}>
                      {item.name} (v{item.current_version ?? "?"}) — {statusName(item.approval_status)}
                    </button>
                    <span className="muted">
                      {" "}· {item.source_name} · {item.enabled ? "활성" : "비활성"}
                      {" "}· {item.compatibility?.compatible ? "Catalog 호환" : "Catalog 미호환/확인 불가"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}
      </section>
      {selected !== null ? (
        <section className="qa-panel" aria-labelledby="review-detail-heading">
          <h2 id="review-detail-heading">템플릿 상세 검토</h2>
          {detailBusy ? <p role="status">상세 검증 중…</p> : null}
          {detailError ? <div role="alert" className="banner banner-error">{detailError}</div> : null}
          {detail && safety ? (
            <div data-testid="template-review-detail">
              <p><strong>{detail.name}</strong> · {detail.stable_key} · v{detail.version.version}</p>
              <p>승인 상태: {statusName(detail.version.approval_status)} ·
                {detail.enabled ? " 활성" : " 비활성"}</p>
              <p>Catalog: 고정 Revision #{detail.version.compatibility.pinned_revision_id},
                현재 Revision #{detail.version.compatibility.current_revision_id ?? "없음"} ·
                {detail.version.compatibility.compatible ? " 호환" : " 불일치 (실행 불가)"}</p>
              <p>SQL 안전성: <strong>{safety.safe ? "검증 통과 (승인 아님)" : "검증 실패"}</strong>
                {" "}· 문장 {safety.statement_count}개</p>
              <p>파라미터 이름/형식: {detail.version.parameter_schema.map(
                (p) => `${p.name} (${p.type})`,
              ).join(", ") || "없음"}</p>
              <p>행 수 상한: {detail.version.row_limit}, 제한 시간: {detail.version.timeout_seconds}초</p>
              {safety.issues.length > 0 ? (
                <ul>{safety.issues.map((issue, i) => (
                  <li key={i}><code>{issue.code}</code> — {issue.message}</li>
                ))}</ul>
              ) : null}
              <h3>등록된 SQL (검토용·실행 불가)</h3>
              <pre className="qb-sql">{detail.version.sql_text}</pre>
            </div>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
