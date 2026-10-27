import { useEffect, useRef, useState } from "react";
import { reviewInspectorTarget } from "../api/inspectorTargetReview";
import type { InspectorTargetReview } from "../types/inspectorTargetReview";

const MISMATCH_LABELS: Record<InspectorTargetReview["mismatch_fields"][number], string> = {
  environment: "Environment",
  source_name: "Source",
  dbms_type: "DBMS",
  host: "Host",
  port: "Port",
  database_name_vs_service_name: "Database Name ↔ Oracle Service Name (단순 문자열)",
  username: "Username",
};

const CONFIG_LABELS: Record<InspectorTargetReview["inspector_configuration_state"], string> = {
  DISABLED: "Inspector 비활성",
  ENV_BLOCKED: "현재 환경에서 Inspector 실행 차단",
  INVALID: "서버 Inspector 설정 누락 또는 형식 불일치",
  CONFIGURED_UNVERIFIED: "서버 Inspector 설정 형식 확인 (미검증)",
};

const COMPARE_LABELS: Record<InspectorTargetReview["comparison_state"], string> = {
  NOT_COMPARABLE: "설정 구조 대조 불가",
  TARGET_METADATA_MISMATCH: "프로필과 Inspector 설정의 구조 불일치",
  STRUCTURAL_MATCH_UNVERIFIED: "프로필과 Inspector 설정의 문자열/숫자 일치 (미검증)",
};

/**
 * Explicit, non-destructive comparison of existing server-only Inspector
 * operator config against a selected Connection Profile.
 * No target modification, permission grant or live connection controls.
 */
export function InspectorTargetReviewPanel({ profileId }: { profileId: number }) {
  const generation = useRef(0);
  const [review, setReview] = useState<InspectorTargetReview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    generation.current += 1;
    setReview(null);
    setError(null);
    setLoading(false);
    return () => { generation.current += 1; };
  }, [profileId]);

  async function runReview(): Promise<void> {
    if (loading) return;
    const requestId = ++generation.current;
    setReview(null);
    setError(null);
    setLoading(true);
    try {
      const result = await reviewInspectorTarget(profileId);
      if (generation.current !== requestId) return;
      if (
        result.profile_id !== profileId ||
        result.connection_authorized !== false ||
        result.live_connection_tested !== false ||
        result.inspector_bound_to_profile !== false ||
        result.credential_values_resolved !== false
      ) {
        setError("안전한 설정 대조 응답을 확인할 수 없습니다.");
        return;
      }
      setReview(result);
    } catch {
      if (generation.current === requestId) {
        setError("설정 대조에 실패했습니다. 관리자 권한과 서버 설정을 확인하세요.");
      }
    } finally {
      if (generation.current === requestId) setLoading(false);
    }
  }

  return (
    <div className="cp-target-review" data-testid="inspector-target-review">
      <h4>Schema Inspector Target 설정 대조</h4>
      <p className="dd-guidance">
        Inspector는 서버 설정을 독립적으로 사용합니다. 아래 결과는 설정값의 형식·문자열 비교이며,
        실접속·복제 DB 진위·계정 권한·군/DBA 승인·Preflight 증빙을 확인하지 않습니다.
      </p>
      <div className="dd-action-row">
        <button type="button" className="dd-secondary-btn" onClick={() => { void runReview(); }}
          disabled={loading}>
          {loading ? "설정 대조 중…" : "설정 대조 조회 (연결 없음)"}
        </button>
      </div>
      {error ? <p className="banner banner-error" role="alert">{error}</p> : null}
      {review ? (
        <div className="cp-target-review-result" role="status">
          <p><strong>Inspector 설정:</strong> {CONFIG_LABELS[review.inspector_configuration_state]}</p>
          <p><strong>구조 비교:</strong> {COMPARE_LABELS[review.comparison_state]}</p>
          {review.mismatch_fields.length > 0 ? (
            <p><strong>불일치 항목:</strong> {review.mismatch_fields
              .map((field) => MISMATCH_LABELS[field] ?? "기타 항목").join(", ")}</p>
          ) : null}
          {review.mismatch_fields.includes("username") ? (
            <p className="dd-guidance">
              메타데이터 검사 계정과 조회 계정은 달라야 하므로 Username 불일치는
              예상되는 결과입니다. 실제 분석 가능 여부는 별도의 「Inspector 연계 조건 확인」으로
              판단하며, 이 설정 대조는 승인이나 접근 허가가 아닙니다.
            </p>
          ) : null}
          <p className="dd-guidance">
            Profile 사용 상태: {review.profile_enabled ? "활성" : "비활성"} ·
            Inspector와 Profile 자동 바인딩 없음 · 실제 연결 미실행 · 연결 승인 없음
          </p>
        </div>
      ) : null}
    </div>
  );
}
