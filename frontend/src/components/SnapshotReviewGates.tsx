import type { SnapshotReviewPreview } from "../types/schemaSnapshot";
import {
  isSafeSnapshotReviewPreview, SNAPSHOT_REVIEW_GATE_LABELS, SNAPSHOT_REVIEW_REQUIRED_GATES,
} from "../utils/snapshotReviewGates";

/** Advisory-only S-05 gate list. No new requests, commands or approval actions. */
export function SnapshotReviewGates({ preview }: { preview: SnapshotReviewPreview }) {
  if (!isSafeSnapshotReviewPreview(preview)) {
    return <div role="alert" className="banner banner-error" data-testid="snapshot-gates-invalid">
      Snapshot 검토 Gate 계약을 확인할 수 없습니다. 관리자에게 문의하세요.
    </div>;
  }

  return (
    <section className="dd-index-section snapshot-gates" aria-label="Snapshot Gate 안내"
      data-testid="snapshot-review-gates">
      <h4>후속 Gate 안내 (조회 전용 · 완료 판정 아님)</h4>
      <div className="banner banner-warn">
        내부 Snapshot 및 WARNING 후보 확인은 독립 Preflight VERIFIED,
        Catalog READY 승인, 자동 Import·활성화 증빙이 아닙니다.
      </div>
      <p className="dd-guidance" data-testid="snapshot-gate-revision">
        {preview.is_latest
          ? `선택한 Snapshot #${preview.revision_id}: 현재 최신 Revision · 변경 검토 필요`
          : `선택한 Snapshot #${preview.revision_id}: 최신 #${preview.latest_revision_id}로 대체됨 · 이력 조회만 가능`}
      </p>
      <p className="dd-guidance">
        저장 Snapshot 무결성 및 후보 형식 검사는 내부 검증이며, 아래 항목은
        별도 확인해야 할 절차입니다. 각 Gate의 실제 완료 여부는 이 API로 판정할 수 없습니다.
      </p>
      <ol className="dd-path-list" aria-label="필요한 후속 검토 단계">
        {SNAPSHOT_REVIEW_REQUIRED_GATES.map((gate) => (
          <li key={gate}>
            <code>{gate}</code> — {SNAPSHOT_REVIEW_GATE_LABELS[gate]}
            <span className="dd-path-meta"> · 별도 증빙·운영 판단 필요</span>
          </li>
        ))}
      </ol>
      <p className="dd-guidance">
        Preflight: NOT_VERIFIED · 후보: WARNING · Activation eligible: false
      </p>
    </section>
  );
}
