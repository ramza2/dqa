import { useState } from "react";
import type { SnapshotSummary, SnapshotReviewPreview } from "../types/schemaSnapshot";
import { compareOfflineSummary, OFFLINE_SUMMARY_LIMIT, parseOfflineMetadataSummary } from "../utils/offlineMetadataSummary";
import type { OfflineMetadataSummary } from "../utils/offlineMetadataSummary";

const statusText: Record<string, string> = {
  SNAPSHOT_PREVIEW_UNAVAILABLE: "저장 Snapshot 무결성 검토가 준비되지 않아 대조할 수 없습니다.",
  OUT_OF_SCOPE: "선택한 Snapshot이 합성 Oracle Mock 범위 밖입니다.",
  SUPERSEDED: "선택한 Snapshot이 최신 Revision이 아니므로 비교하지 않습니다.",
  FINGERPRINT_MATCH_UNTRUSTED: "입력 요약의 Fingerprint와 개수가 같습니다. 파일 진위나 DBA 승인을 증명하지 않습니다.",
  FINGERPRINT_DIFFERENCE_UNTRUSTED: "입력 요약의 Fingerprint가 다릅니다. 실제 파일을 별도로 검증하세요.",
  COUNT_CONFLICT_UNTRUSTED: "Fingerprint가 같지만 객체 개수가 다릅니다. 입력 요약을 신뢰하지 마세요.",
};

/** Local paste of a sanitized CLI report. No raw file upload, fetch or persistence. */
export function OfflineMetadataSummaryPanel({
  snapshot, preview,
}: { snapshot: SnapshotSummary; preview: SnapshotReviewPreview | null }) {
  const [text, setText] = useState("");
  const [report, setReport] = useState<OfflineMetadataSummary | null>(null);
  const [invalid, setInvalid] = useState(false);
  const status = report ? compareOfflineSummary(report, snapshot, preview) : null;
  return (
    <section className="dd-index-section" data-testid="offline-summary-panel">
      <h3>오프라인 메타데이터 요약 대조 (로컬·비공식)</h3>
      <p className="dd-guidance">
        합성 Mock CLI의 --summary-json 출력만 입력하세요. 원본 메타데이터, 환자정보, 서명 파일은 입력하지 마세요.
        이 입력은 서버로 전송하거나 저장하지 않습니다.
      </p>
      <div className="banner banner-warn">
        해시 일치도 출처 인증·독립 DBA Preflight·Catalog READY·DEMIS 접근 승인이 아닙니다.
      </div>
      <label className="dd-field">
        <span>오프라인 검증 요약 JSON (최대 2KB)</span>
        <textarea aria-label="오프라인 검증 요약 JSON" rows={3}
          maxLength={OFFLINE_SUMMARY_LIMIT} value={text}
          onChange={(event) => { setText(event.target.value); setReport(null); setInvalid(false); }}
          placeholder='{"format":"dqa-offline-metadata-summary-v1", ...}' />
      </label>
      <div className="dd-action-row">
        <button type="button" className="dd-secondary-btn" onClick={() => {
          const valid = parseOfflineMetadataSummary(text);
          setReport(valid); setInvalid(valid === null);
        }}>요약 로컬 대조</button>
        <button type="button" className="dd-secondary-btn" onClick={() => {
          setText(""); setReport(null); setInvalid(false);
        }}>요약 지우기</button>
      </div>
      {invalid ? <div role="alert" className="banner banner-error" data-testid="offline-summary-invalid">
        허용된 형식과 미승인 상태를 확인하지 못했습니다. 입력 원문은 표시하지 않습니다.
      </div> : null}
      {report && status ? (
        <div data-testid="offline-summary-result">
          <p className="dd-guidance"><strong>로컬 대조 결과: {status}</strong> — {statusText[status]}</p>
          <div className="status-grid dd-meta-grid">
            <div className="status-item"><span className="label">출처 주장</span><span className="value">{report.claim_binding}</span></div>
            <div className="status-item"><span className="label">검토 초안</span><span className="value">{report.review_draft_status}</span></div>
            <div className="status-item"><span className="label">독립 검증</span><span className="value">NOT_VERIFIED</span></div>
            <div className="status-item"><span className="label">Catalog 후보/활성화</span><span className="value">WARNING / false</span></div>
          </div>
          <p className="dd-guidance">
            화면은 원본을 재검증하지 않습니다. 실제 Snapshot 구조 대조에는 별도 내부 M2-1G 검증이 필요합니다.
          </p>
        </div>
      ) : null}
    </section>
  );
}
