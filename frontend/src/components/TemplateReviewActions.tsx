import { useEffect, useRef, useState } from "react";
import {
  getReviewTemplate, getReviewTemplateSqlSafety, postReviewAction,
  type ReviewAction, type TemplateReviewActor,
} from "../api/templateReview";
import type { ReviewTemplateDetail, TemplateSqlSafetyReview } from "../types/templateReview";
import { CatalogApiError } from "../types/catalog";

function actionError(error: unknown): string {
  if (error instanceof CatalogApiError) {
    if (error.status === 401) return "인증이 필요합니다.";
    if (error.status === 403) return "현재 계정에는 해당 검토 작업 권한이 없습니다.";
    if (error.status === 409) return "템플릿이 변경되었거나 상태가 달라졌습니다. 목록을 새로고침하세요.";
    if (error.status === 422) return "요청을 처리할 수 없습니다. SQL 안전성·입력값을 다시 확인하세요.";
    return error.message;
  }
  return "검토 작업이 실패했습니다. 현재 상태를 새로고침하세요.";
}

function matchesSnapshot(
  initial: ReviewTemplateDetail, current: ReviewTemplateDetail,
  initialSafety: TemplateSqlSafetyReview, newSafety: TemplateSqlSafetyReview,
): boolean {
  return initial.id === current.id &&
    initial.current_version_id === current.current_version_id &&
    initial.current_version === current.current_version &&
    initial.approval_status === current.approval_status &&
    initial.updated_at === current.updated_at &&
    initial.version.sql_text === current.version.sql_text &&
    JSON.stringify(initial.version.parameter_schema) === JSON.stringify(current.version.parameter_schema) &&
    initial.version.compatibility.pinned_revision_id === current.version.compatibility.pinned_revision_id &&
    initial.version.compatibility.pinned_schema_fingerprint === current.version.compatibility.pinned_schema_fingerprint &&
    initial.version.compatibility.current_revision_id === current.version.compatibility.current_revision_id &&
    initial.version.compatibility.current_schema_fingerprint === current.version.compatibility.current_schema_fingerprint &&
    initial.version.compatibility.compatible === current.version.compatibility.compatible &&
    initialSafety.version_id === newSafety.version_id &&
    initialSafety.version === newSafety.version &&
    initialSafety.safe === newSafety.safe &&
    newSafety.template_id === current.id;
}

export function TemplateReviewActions({
  actor, detail, safety, onCompleted,
}: {
  actor: TemplateReviewActor;
  detail: ReviewTemplateDetail;
  safety: TemplateSqlSafetyReview;
  onCompleted: (message: string) => void;
}) {
  const mounted = useRef(true);
  const busyRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState<ReviewAction | "">("");

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  const isAdmin = actor.roles.includes("administrator");
  const canAuthor = isAdmin || actor.roles.includes("template_author");
  const canApprove = isAdmin || actor.roles.includes("template_approver");
  const compatible = detail.compatibility?.compatible === true &&
    detail.version.compatibility.compatible === true;
  const eligible = compatible && safety.safe && !detail.enabled;
  const canSubmit = canAuthor && detail.approval_status === "DRAFT" && eligible;
  const canDecide = canApprove && detail.approval_status === "IN_REVIEW" && !detail.enabled;
  const canAccept = canDecide && eligible;
  const canReject = canDecide;

  const execute = async () => {
    if (busyRef.current || !confirmed || !choice) return;
    if (choice === "submit-review" && !canSubmit) return;
    if (choice === "approve" && !canAccept) return;
    if (choice === "reject" && (!canReject || !note.trim())) return;
    busyRef.current = true;
    setBusy(true);
    setError(null);
    try {
      // Re-check current selection before the mutation; backend checks
      // expected_version_id + expected_updated_at under FOR UPDATE.
      const [latest, latestSafety] = await Promise.all([
        getReviewTemplate(detail.id), getReviewTemplateSqlSafety(detail.id),
      ]);
      if (!mounted.current) return;
      if (!matchesSnapshot(detail, latest, safety, latestSafety)) {
        throw new Error("STALE_REVIEW_SELECTION");
      }
      if (choice !== "reject" && (!latestSafety.safe ||
          !latest.compatibility?.compatible || !latest.version.compatibility.compatible)) {
        throw new Error("REVIEW_BLOCKED");
      }
      const result = await postReviewAction(detail.id, choice, {
        note: note.trim(), expected_version_id: detail.version.id,
        expected_updated_at: detail.updated_at,
      });
      if (!mounted.current) return;
      const expectedStatus = choice === "submit-review" ? "IN_REVIEW" :
        choice === "approve" ? "APPROVED" : "REJECTED";
      if (result.id !== detail.id || result.current_version_id !== detail.version.id ||
          result.approval_status !== expectedStatus ||
          (choice === "approve" && result.enabled)) {
        setError("서버 처리 결과 확인이 필요합니다. 목록을 새로고침하세요.");
        return;
      }
      onCompleted(choice === "submit-review" ? "검토 제출 완료. 목록을 다시 조회하세요." :
        choice === "approve" ? "승인 완료. 템플릿은 자동 활성화되지 않습니다." :
          "반려 완료. 목록을 다시 조회하세요.");
    } catch (err) {
      if (mounted.current) setError(err instanceof Error &&
        (err.message === "STALE_REVIEW_SELECTION" || err.message === "REVIEW_BLOCKED")
        ? "검토 중 SQL·버전·Catalog 상태가 변경됐습니다. 다시 조회하세요."
        : actionError(err));
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  if (!canAuthor && !canApprove) return (
    <p role="status" className="muted">조회 권한만 있습니다. 검토 상태 변경은 할 수 없습니다.</p>
  );

  return (
    <section className="qb-review-actions" data-testid="template-review-actions">
      <h3>권한별 검토 작업</h3>
      <p className="muted">
        작성자는 DRAFT를 검토 제출할 수 있고, 승인자는 IN_REVIEW를 승인·반려할 수 있습니다.
        최종 권한과 상태 검사는 서버에서 다시 수행합니다.
      </p>
      {!eligible && <p className="banner banner-warn" role="status">
        SQL 안전성·Catalog 호환성 또는 활성 상태에 문제가 있어 승인/제출을 제한합니다.
      </p>}
      <div className="qa-actions">
        {canSubmit && <button type="button" onClick={() => { setChoice("submit-review"); setConfirmed(false); }}>
          검토 제출 선택
        </button>}
        {canAccept && <button type="button" onClick={() => { setChoice("approve"); setConfirmed(false); }}>
          승인 선택
        </button>}
        {canReject && <button type="button" onClick={() => { setChoice("reject"); setConfirmed(false); }}>
          반려 선택
        </button>}
      </div>
      {choice && (
        <div className="qb-action-confirm">
          <strong>{choice === "submit-review" ? "검토 제출" : choice === "approve" ? "승인" : "반려"} 최종 확인</strong>
          <label className="param-field">
            <span className="param-label">검토 메모 {choice === "reject" ? "(필수)" : "(선택)"}</span>
            <textarea aria-label="검토 메모" maxLength={2000} value={note}
              disabled={busy} onChange={(e) => { setNote(e.target.value); setConfirmed(false); }} />
          </label>
          <label className="qb-review-confirm">
            <input type="checkbox" checked={confirmed} disabled={busy}
              onChange={(e) => setConfirmed(e.target.checked)} />
            선택한 템플릿 v{detail.version.version}, SQL·Catalog·안전성 확인
          </label>
          <div className="qa-actions">
            <button type="button" disabled={busy || !confirmed ||
              (choice === "reject" && !note.trim())}
              onClick={() => void execute()}>
              {busy ? "서버 재검증 중…" : "선택한 작업 확정"}
            </button>
            <button type="button" disabled={busy} onClick={() => {
              setChoice(""); setConfirmed(false); setError(null);
            }}>취소</button>
          </div>
        </div>
      )}
      {error && <div role="alert" className="banner banner-error">{error}</div>}
    </section>
  );
}
