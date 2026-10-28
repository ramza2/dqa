import { useEffect, useRef, useState } from "react";
import {
  approveReviewTemplate,
  createReviewTemplate,
  createReviewTemplateVersion,
  disableReviewTemplate,
  enableReviewTemplate,
  getReviewTemplate,
  getReviewTemplateSqlSafety,
  listReviewEvents,
  listReviewTemplates,
  rejectReviewTemplate,
  submitReviewTemplate,
  updateReviewTemplate,
} from "../api/templateReview";
import type {
  ReviewTemplateDetail,
  ReviewTemplateList,
  ReviewTemplateSummary,
  TemplateParameterSchema,
  TemplateReviewEvent,
  TemplateSqlSafetyReview,
} from "../types/templateReview";
import { formatAssistantError } from "../utils/queryAssistant";
import { CatalogApiError } from "../types/catalog";

const PAGE_SIZE = 50;

type DraftForm = {
  stable_key: string;
  name: string;
  description: string;
  source_name: string;
  target_schemas: string;
  sql_text: string;
  parameter_schema_json: string;
  row_limit: string;
  timeout_seconds: string;
};

const EMPTY_CREATE: DraftForm = {
  stable_key: "",
  name: "",
  description: "",
  source_name: "",
  target_schemas: "DEMIS_OWNER",
  sql_text: "SELECT 1 FROM dual",
  parameter_schema_json: "[]",
  row_limit: "100",
  timeout_seconds: "30",
};

function reviewErrorMessage(error: unknown): string {
  if (error instanceof CatalogApiError) {
    if (error.status === 403 && error.code === "AUTHORIZATION_DENIED") {
      return "요청한 템플릿 작업 권한이 없습니다.";
    }
    if (error.code === "QUERY_TEMPLATE_SQL_UNSAFE") {
      return "SQL 안전성 검증 실패로 서버가 승인·활성화를 차단했습니다.";
    }
    if (error.code === "QUERY_TEMPLATE_INCOMPATIBLE_CATALOG") {
      return "Active Catalog 불일치로 서버가 승인·활성화를 차단했습니다.";
    }
    if (error.code === "QUERY_TEMPLATE_INVALID_TRANSITION") {
      return "상태·버전 전이가 허용되지 않습니다. 목록을 새로고침하세요.";
    }
    if (error.code === "QUERY_TEMPLATE_NOT_DRAFT") {
      return "DRAFT가 아니거나 활성 템플릿이라 수정할 수 없습니다.";
    }
  }
  return formatAssistantError(error).message;
}

function statusName(value: string | null): string {
  return ({
    DRAFT: "초안", IN_REVIEW: "검토 중",
    APPROVED: "승인됨", REJECTED: "반려됨",
  } as Record<string, string>)[value ?? ""] ?? "상태 미지정";
}

function parseSchemas(raw: string): string[] {
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

function parseParameters(raw: string): TemplateParameterSchema[] {
  const parsed = JSON.parse(raw) as unknown;
  if (!Array.isArray(parsed)) {
    throw new Error("parameter_schema는 JSON 배열이어야 합니다.");
  }
  return parsed as TemplateParameterSchema[];
}

function formFromDetail(detail: ReviewTemplateDetail): DraftForm {
  return {
    stable_key: detail.stable_key,
    name: detail.name,
    description: detail.description ?? "",
    source_name: detail.source_name,
    target_schemas: detail.target_schemas.join(", "),
    sql_text: detail.version.sql_text,
    parameter_schema_json: JSON.stringify(detail.version.parameter_schema, null, 2),
    row_limit: String(detail.version.row_limit),
    timeout_seconds: String(detail.version.timeout_seconds),
  };
}

function detailMatchesSummary(
  detail: ReviewTemplateDetail,
  safety: TemplateSqlSafetyReview,
  item: ReviewTemplateSummary,
): boolean {
  return detail.id === item.id
    && detail.source_name === item.source_name
    && detail.stable_key === item.stable_key
    && detail.current_version_id === item.current_version_id
    && detail.current_version === item.current_version
    && detail.approval_status === item.approval_status
    && detail.version.id === detail.current_version_id
    && detail.version.version === detail.current_version
    && detail.version.approval_status === detail.approval_status
    && safety.template_id === detail.id
    && safety.version_id === detail.version.id
    && safety.version === detail.version.version
    && !!detail.compatibility
    && detail.compatibility.pinned_revision_id
      === detail.version.compatibility.pinned_revision_id
    && detail.compatibility.pinned_schema_fingerprint
      === detail.version.compatibility.pinned_schema_fingerprint;
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
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState<DraftForm>(EMPTY_CREATE);
  const [editForm, setEditForm] = useState<DraftForm | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [rejectNote, setRejectNote] = useState("");
  const [events, setEvents] = useState<TemplateReviewEvent[] | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
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
    setEditForm(null);
    setActionError(null);
    setActionNotice(null);
    setReviewNote("");
    setRejectNote("");
    setEvents(null);
    setEventsError(null);
  };

  const clearList = () => {
    sequence.current++;
    clearDetail();
    setPage(null);
    setListError(null);
    setListBusy(false);
  };

  const loadList = async (offset = 0, options?: { keepDetail?: boolean }) => {
    const seq = ++sequence.current;
    if (!options?.keepDetail) clearDetail();
    if (!options?.keepDetail) setPage(null);
    setListError(null);
    setListBusy(true);
    try {
      const result = await listReviewTemplates(sourceName, offset);
      if (!mounted.current || seq !== sequence.current) return;
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

  const applyDetailPair = (
    nextDetail: ReviewTemplateDetail,
    nextSafety: TemplateSqlSafetyReview,
    expected?: ReviewTemplateSummary,
  ): boolean => {
    if (expected && !detailMatchesSummary(nextDetail, nextSafety, expected)) {
      setDetailError("버전·상태 또는 Catalog가 변경되었습니다. 목록을 새로고침하고 다시 선택하세요.");
      setDetail(null);
      setSafety(null);
      setEditForm(null);
      return false;
    }
    if (!expected) {
      if (nextSafety.template_id !== nextDetail.id
          || nextSafety.version_id !== nextDetail.version.id
          || nextSafety.version !== nextDetail.version.version
          || nextDetail.version.id !== nextDetail.current_version_id
          || nextDetail.version.version !== nextDetail.current_version
          || nextDetail.version.approval_status !== nextDetail.approval_status) {
        setDetailError("버전·상태 또는 Catalog가 변경되었습니다. 목록을 새로고침하고 다시 선택하세요.");
        setDetail(null);
        setSafety(null);
        setEditForm(null);
        return false;
      }
    }
    setDetail(nextDetail);
    setSafety(nextSafety);
    setEditForm(formFromDetail(nextDetail));
    setSelected(nextDetail.id);
    return true;
  };

  const chooseTemplate = async (item: ReviewTemplateSummary) => {
    const seq = ++detailSequence.current;
    setSelected(item.id);
    setDetail(null);
    setSafety(null);
    setDetailError(null);
    setActionError(null);
    setActionNotice(null);
    setEvents(null);
    setEventsError(null);
    setDetailBusy(true);
    try {
      const [nextDetail, nextSafety] = await Promise.all([
        getReviewTemplate(item.id), getReviewTemplateSqlSafety(item.id),
      ]);
      if (!mounted.current || seq !== detailSequence.current) return;
      applyDetailPair(nextDetail, nextSafety, item);
    } catch (error) {
      if (mounted.current && seq === detailSequence.current) {
        setDetailError(reviewErrorMessage(error));
      }
    } finally {
      if (mounted.current && seq === detailSequence.current) setDetailBusy(false);
    }
  };

  const refreshSelected = async (templateId: number) => {
    const seq = ++detailSequence.current;
    setDetailBusy(true);
    setDetailError(null);
    try {
      const [nextDetail, nextSafety] = await Promise.all([
        getReviewTemplate(templateId), getReviewTemplateSqlSafety(templateId),
      ]);
      if (!mounted.current || seq !== detailSequence.current) return null;
      if (!applyDetailPair(nextDetail, nextSafety)) return null;
      return nextDetail;
    } catch (error) {
      if (mounted.current && seq === detailSequence.current) {
        setDetailError(reviewErrorMessage(error));
      }
      return null;
    } finally {
      if (mounted.current && seq === detailSequence.current) setDetailBusy(false);
    }
  };

  const loadEvents = async (templateId: number) => {
    setEventsError(null);
    try {
      const result = await listReviewEvents(templateId);
      if (!mounted.current || selected !== templateId) return;
      if (!Array.isArray(result.items)
          || result.items.some((ev) => ev.template_id !== templateId)) {
        setEventsError("검토 이력 응답이 선택한 템플릿과 일치하지 않습니다.");
        setEvents(null);
        return;
      }
      setEvents(result.items);
    } catch (error) {
      if (mounted.current && selected === templateId) {
        setEvents(null);
        setEventsError(reviewErrorMessage(error));
      }
    }
  };

  const runMutation = async (
    expected: ReviewTemplateDetail,
    action: () => Promise<ReviewTemplateDetail>,
    successMessage: string,
  ) => {
    setActionBusy(true);
    setActionError(null);
    setActionNotice(null);
    try {
      const result = await action();
      if (result.id !== expected.id) {
        setActionError("응답 템플릿이 선택과 일치하지 않습니다.");
        return;
      }
      setActionNotice(successMessage);
      await refreshSelected(expected.id);
      if (page) await loadList(page.offset, { keepDetail: true });
    } catch (error) {
      setActionError(reviewErrorMessage(error));
    } finally {
      if (mounted.current) setActionBusy(false);
    }
  };

  const onCreate = async () => {
    setActionBusy(true);
    setActionError(null);
    setActionNotice(null);
    try {
      const parameters = parseParameters(createForm.parameter_schema_json);
      const created = await createReviewTemplate({
        stable_key: createForm.stable_key.trim(),
        name: createForm.name.trim(),
        description: createForm.description.trim() || null,
        source_name: createForm.source_name.trim(),
        target_schemas: parseSchemas(createForm.target_schemas),
        sql_text: createForm.sql_text,
        parameter_schema: parameters,
        row_limit: Number(createForm.row_limit),
        timeout_seconds: Number(createForm.timeout_seconds),
      });
      setShowCreate(false);
      setCreateForm(EMPTY_CREATE);
      setActionNotice("DRAFT 템플릿을 생성했습니다.");
      setSourceName(created.source_name);
      await loadList(0);
      await refreshSelected(created.id);
    } catch (error) {
      setActionError(
        error instanceof SyntaxError
          ? "parameter_schema JSON을 해석할 수 없습니다."
          : reviewErrorMessage(error),
      );
    } finally {
      if (mounted.current) setActionBusy(false);
    }
  };

  const onSaveDraft = async () => {
    if (!detail || !editForm || detail.approval_status !== "DRAFT") return;
    try {
      const parameters = parseParameters(editForm.parameter_schema_json);
      await runMutation(
        detail,
        () => updateReviewTemplate(detail.id, {
          name: editForm.name.trim(),
          description: editForm.description.trim() || null,
          target_schemas: parseSchemas(editForm.target_schemas),
          sql_text: editForm.sql_text,
          parameter_schema: parameters,
          row_limit: Number(editForm.row_limit),
          timeout_seconds: Number(editForm.timeout_seconds),
        }),
        "DRAFT를 저장했습니다.",
      );
    } catch (error) {
      setActionError(
        error instanceof SyntaxError
          ? "parameter_schema JSON을 해석할 수 없습니다."
          : reviewErrorMessage(error),
      );
    }
  };

  const canApproveOrEnable = Boolean(
    detail && safety
      && safety.safe
      && detail.version.compatibility.compatible,
  );

  return (
    <main className="workflow-home" data-testid="template-review-portal">
      <header className="workflow-hero">
        <h1>Query Template 작성·검토</h1>
        <p>
          기존 서버 API로 DRAFT 작성·수정, 검토 제출, 승인·반려, 이력 조회,
          정책에 따른 활성/비활성을 수행합니다.
        </p>
        <p className="workflow-notice">
          <strong>서버 권한·검증이 최종 기준</strong>입니다. 화면의 SQL 안전성 표시만으로
          승인·활성화를 판단하지 않으며, M3-B SQL 미리보기는 자동 저장·승격되지 않습니다.
          작성자(`TEMPLATE_AUTHOR`)와 승인자(`TEMPLATE_APPROVE`) 권한은 서버에서 분리됩니다.
        </p>
      </header>

      <section className="qa-panel" aria-labelledby="review-create-heading">
        <h2 id="review-create-heading">DRAFT 작성</h2>
        <div className="qa-actions">
          <button type="button" disabled={actionBusy}
            onClick={() => { setShowCreate((v) => !v); setActionError(null); }}>
            {showCreate ? "작성 폼 닫기" : "새 템플릿 DRAFT 작성"}
          </button>
        </div>
        {showCreate ? (
          <div data-testid="template-create-form" className="template-author-form">
            {(
              [
                ["stable_key", "stable_key", createForm.stable_key],
                ["name", "이름", createForm.name],
                ["source_name", "Source 이름", createForm.source_name],
                ["target_schemas", "대상 스키마 (쉼표 구분)", createForm.target_schemas],
                ["row_limit", "행 수 상한", createForm.row_limit],
                ["timeout_seconds", "제한 시간(초)", createForm.timeout_seconds],
              ] as const
            ).map(([key, label, value]) => (
              <label key={key} className="param-field">
                <span className="param-label">{label}</span>
                <input aria-label={`작성 ${label}`} value={value}
                  onChange={(e) => setCreateForm({ ...createForm, [key]: e.target.value })} />
              </label>
            ))}
            <label className="param-field">
              <span className="param-label">설명</span>
              <input aria-label="작성 설명" value={createForm.description}
                onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })} />
            </label>
            <label className="param-field">
              <span className="param-label">SQL (저장만 · 실행 아님)</span>
              <textarea aria-label="작성 SQL" rows={6} value={createForm.sql_text}
                onChange={(e) => setCreateForm({ ...createForm, sql_text: e.target.value })} />
            </label>
            <label className="param-field">
              <span className="param-label">parameter_schema (JSON 배열)</span>
              <textarea aria-label="작성 parameter_schema" rows={5}
                value={createForm.parameter_schema_json}
                onChange={(e) => setCreateForm({
                  ...createForm, parameter_schema_json: e.target.value,
                })} />
            </label>
            <div className="qa-actions">
              <button type="button" disabled={actionBusy} onClick={() => void onCreate()}>
                DRAFT 생성
              </button>
            </div>
          </div>
        ) : null}
      </section>

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
                      disabled={detailBusy || actionBusy} onClick={() => void chooseTemplate(item)}>
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
          <h2 id="review-detail-heading">템플릿 상세·작업</h2>
          {detailBusy ? <p role="status">상세 검증 중…</p> : null}
          {detailError ? <div role="alert" className="banner banner-error">{detailError}</div> : null}
          {actionError ? <div role="alert" className="banner banner-error">{actionError}</div> : null}
          {actionNotice ? <div role="status" className="banner banner-empty">{actionNotice}</div> : null}
          {detail && safety && editForm ? (
            <div data-testid="template-review-detail">
              <p><strong>{detail.name}</strong> · {detail.stable_key} · v{detail.version.version}</p>
              <p>승인 상태: {statusName(detail.version.approval_status)} ·
                {detail.enabled ? " 활성" : " 비활성"}</p>
              <p>Catalog: 고정 Revision #{detail.version.compatibility.pinned_revision_id},
                현재 Revision #{detail.version.compatibility.current_revision_id ?? "없음"} ·
                {detail.version.compatibility.compatible ? " 호환" : " 불일치 (승인·활성화 차단)"}</p>
              <p>SQL 안전성: <strong>{safety.safe ? "검증 통과 (승인 아님)" : "검증 실패"}</strong>
                {" "}· 문장 {safety.statement_count}개
                {!safety.safe || !detail.version.compatibility.compatible
                  ? " · 서버가 승인·활성화를 거부합니다"
                  : ""}</p>
              <p>작성자: {detail.version.created_by ?? "미기록"} ·
                승인자: {detail.version.approved_by ?? "미기록"}</p>
              {safety.issues.length > 0 ? (
                <ul>{safety.issues.map((issue, i) => (
                  <li key={i}><code>{issue.code}</code> — {issue.message}</li>
                ))}</ul>
              ) : null}

              {detail.approval_status === "DRAFT" ? (
                <div data-testid="template-draft-editor" className="template-author-form">
                  <h3>DRAFT 수정</h3>
                  <label className="param-field">
                    <span className="param-label">이름</span>
                    <input aria-label="DRAFT 이름" value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })} />
                  </label>
                  <label className="param-field">
                    <span className="param-label">설명</span>
                    <input aria-label="DRAFT 설명" value={editForm.description}
                      onChange={(e) => setEditForm({ ...editForm, description: e.target.value })} />
                  </label>
                  <label className="param-field">
                    <span className="param-label">대상 스키마 (쉼표 구분)</span>
                    <input aria-label="DRAFT 대상 스키마" value={editForm.target_schemas}
                      onChange={(e) => setEditForm({
                        ...editForm, target_schemas: e.target.value,
                      })} />
                  </label>
                  <label className="param-field">
                    <span className="param-label">SQL</span>
                    <textarea aria-label="DRAFT SQL" rows={6} value={editForm.sql_text}
                      onChange={(e) => setEditForm({ ...editForm, sql_text: e.target.value })} />
                  </label>
                  <label className="param-field">
                    <span className="param-label">parameter_schema (JSON)</span>
                    <textarea aria-label="DRAFT parameter_schema" rows={5}
                      value={editForm.parameter_schema_json}
                      onChange={(e) => setEditForm({
                        ...editForm, parameter_schema_json: e.target.value,
                      })} />
                  </label>
                  <label className="param-field">
                    <span className="param-label">행 수 상한</span>
                    <input aria-label="DRAFT 행 수 상한" value={editForm.row_limit}
                      onChange={(e) => setEditForm({ ...editForm, row_limit: e.target.value })} />
                  </label>
                  <label className="param-field">
                    <span className="param-label">제한 시간(초)</span>
                    <input aria-label="DRAFT 제한 시간" value={editForm.timeout_seconds}
                      onChange={(e) => setEditForm({
                        ...editForm, timeout_seconds: e.target.value,
                      })} />
                  </label>
                  <label className="param-field">
                    <span className="param-label">검토 제출 메모 (선택)</span>
                    <input aria-label="검토 제출 메모" value={reviewNote}
                      onChange={(e) => setReviewNote(e.target.value)} />
                  </label>
                  <div className="qa-actions">
                    <button type="button" disabled={actionBusy}
                      onClick={() => void onSaveDraft()}>DRAFT 저장</button>
                    <button type="button" disabled={actionBusy}
                      onClick={() => void runMutation(
                        detail,
                        () => submitReviewTemplate(detail.id, reviewNote.trim() || undefined),
                        "검토 제출했습니다.",
                      )}>검토 제출</button>
                  </div>
                </div>
              ) : (
                <>
                  <p>파라미터 이름/형식: {detail.version.parameter_schema.map(
                    (p) => `${p.name} (${p.type})`,
                  ).join(", ") || "없음"}</p>
                  <p>행 수 상한: {detail.version.row_limit}, 제한 시간: {detail.version.timeout_seconds}초</p>
                  <h3>등록된 SQL (검토용·실행 불가)</h3>
                  <pre className="qb-sql">{detail.version.sql_text}</pre>
                </>
              )}

              {detail.approval_status === "IN_REVIEW" ? (
                <div data-testid="template-approve-actions" className="template-author-form">
                  <h3>승인·반려</h3>
                  <p className="muted">
                    승인·활성화는 서버가 SQL Safety와 Catalog 호환성을 다시 검증합니다.
                    화면 표시만으로 안전하다고 판단하지 마세요.
                  </p>
                  <label className="param-field">
                    <span className="param-label">승인 메모 (선택)</span>
                    <input aria-label="승인 메모" value={reviewNote}
                      onChange={(e) => setReviewNote(e.target.value)} />
                  </label>
                  <label className="param-field">
                    <span className="param-label">반려 사유 (필수)</span>
                    <input aria-label="반려 사유" value={rejectNote}
                      onChange={(e) => setRejectNote(e.target.value)} />
                  </label>
                  <div className="qa-actions">
                    <button type="button" aria-label="승인"
                      disabled={actionBusy || !canApproveOrEnable}
                      onClick={() => void runMutation(
                        detail,
                        () => approveReviewTemplate(detail.id, reviewNote.trim() || undefined),
                        "승인했습니다. 활성 상태는 별도 활성화가 필요합니다.",
                      )}>승인</button>
                    <button type="button" aria-label="반려"
                      disabled={actionBusy || rejectNote.trim() === ""}
                      onClick={() => void runMutation(
                        detail,
                        () => rejectReviewTemplate(detail.id, rejectNote.trim()),
                        "반려했습니다.",
                      )}>반려</button>
                  </div>
                </div>
              ) : null}

              {detail.approval_status === "APPROVED" || detail.approval_status === "REJECTED" ? (
                <div className="qa-actions">
                  <button type="button" disabled={actionBusy}
                    onClick={() => void runMutation(
                      detail,
                      () => createReviewTemplateVersion(detail.id),
                      "새 DRAFT 버전을 만들었습니다.",
                    )}>새 버전 작성</button>
                </div>
              ) : null}

              {detail.approval_status === "APPROVED" ? (
                <div data-testid="template-enable-actions" className="qa-actions">
                  {!detail.enabled ? (
                    <button type="button" aria-label="활성화"
                      disabled={actionBusy || !canApproveOrEnable}
                      onClick={() => void runMutation(
                        detail,
                        () => enableReviewTemplate(detail.id),
                        "활성화했습니다.",
                      )}>활성화</button>
                  ) : (
                    <button type="button" aria-label="비활성화"
                      disabled={actionBusy}
                      onClick={() => void runMutation(
                        detail,
                        () => disableReviewTemplate(detail.id),
                        "비활성화했습니다.",
                      )}>비활성화</button>
                  )}
                </div>
              ) : null}

              <div data-testid="template-review-history">
                <h3>검토 이력</h3>
                <div className="qa-actions">
                  <button type="button" disabled={actionBusy || detailBusy}
                    onClick={() => void loadEvents(detail.id)}>검토 이력 불러오기</button>
                </div>
                {eventsError ? (
                  <div role="alert" className="banner banner-error">{eventsError}</div>
                ) : null}
                {events ? (
                  events.length === 0 ? <p>이력이 없습니다.</p> : (
                    <ul>
                      {events.map((ev) => (
                        <li key={ev.id}>
                          v#{ev.version_id}: {statusName(ev.from_status)} → {statusName(ev.to_status)}
                          {" "}· {ev.actor ?? "actor 미기록"}
                          {ev.note ? ` · ${ev.note}` : ""}
                          {" "}· {ev.created_at}
                        </li>
                      ))}
                    </ul>
                  )
                ) : null}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
