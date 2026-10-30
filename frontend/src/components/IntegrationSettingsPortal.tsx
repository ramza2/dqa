import { useCallback, useEffect, useState } from "react";
import { ServiceClientDraftsPanel } from "./ServiceClientDraftsPanel";
import {
  getIntegrationSettingsStatus,
  type IntegrationSettingsStatus,
} from "../api/integrationSettings";

/** M5-S0: safe visibility only. No secret-editing or client-admission controls. */
export function IntegrationSettingsPortal() {
  const [status, setStatus] = useState<IntegrationSettingsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [showPolicyDrafts, setShowPolicyDrafts] = useState(false);

  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    let active = true;
    getIntegrationSettingsStatus()
      .then((result) => {
        if (!active) return;
        setStatus(result);
        setError(null);
      })
      .catch(() => {
        if (!active) return;
        setStatus(null);
        setError("설정 조회 권한이 없거나 서버 인증 설정이 준비되지 않았습니다.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [revision]);

  return (
    <main className="dd-portal">
      <section className="dd-panel">
        <header className="dd-panel-header">
          <h2>환경 설정 · 연계 보안</h2>
          <span className="muted">관리자 전용 · 현재 상태 조회</span>
        </header>
        <p className="dd-guidance">
          이 화면은 연결 및 보안 설정 상태만 조회합니다. LLM 연결값은 현재 서버 환경에서
          관리하며, 여기서 비밀키를 보거나 수정할 수 없습니다.
        </p>
        <div className="dd-action-row">
          <button type="button" className="dd-secondary-btn" onClick={() => {
            setLoading(true);
            refresh();
          }}>
            상태 새로고침
          </button>
        </div>
        {loading && <p role="status">설정 상태를 확인하는 중입니다.</p>}
        {!loading && error && <p role="alert" className="banner banner-error">{error}</p>}
        {!loading && status && (
          <>
            <section className="qa-panel" aria-label="LLM 연결 상태">
              <h3>선택적 LLM 연결</h3>
              <div className="meta-grid">
                <div className="meta-card">
                  <div className="label">연결 방식</div>
                  <div className="value">OpenAI 호환 API</div>
                </div>
                <div className="meta-card">
                  <div className="label">엔드포인트 설정</div>
                  <div className="value">{status.llm.endpoint_configured ? "설정됨" : "미설정"}</div>
                </div>
                <div className="meta-card">
                  <div className="label">모델</div>
                  <div className="value">{status.llm.model_configured ? status.llm.model : "미설정"}</div>
                </div>
                <div className="meta-card">
                  <div className="label">API 키</div>
                  <div className="value">{status.llm.api_key_present ? "설정됨 (값 비공개)" : "미설정"}</div>
                </div>
              </div>
              <p className="muted">
                '설정됨'은 서버에 연결 정보가 있다는 의미이며 실제 접속 성공이나 사용 승인을 뜻하지 않습니다.
                비임상 메타데이터 연결 시험, URL·모델 변경 및 연결 초기화 기능은 아직 제공되지 않습니다.
                기존 설정은 서버 환경에서 관리하며, 향후 승인된 비밀관리·접속대상 제한·변경 감사가 마련되면 관리자 기능으로 제공할 예정입니다.
              </p>
              <p className="muted">
                LLM은 선택 기능입니다. 연결 설정 여부만으로 임상정보 외부 전송이 허용되지
                않습니다. 자연어 요청 원문 전송:{" "}
                <strong>{status.llm.raw_request_egress_allowed ? "설정상 허용 (기관 정책 승인 별도 확인 필요)" : "차단"}</strong>
              </p>
            </section>
            <section className="qa-panel" aria-label="외부 서비스 접근 제어">
              <h3>FHIR·외부 시스템 접근 제어</h3>
              <p>
                서비스 클라이언트 정책 초안 등록·감사 기능만 제공됩니다. 서비스키 발급/회수,
                실제 호출자 인증 및 IP 허용목록 강제는 아직 구현되지 않았습니다.
              </p>
              <p className="muted">
                인증 기능 개발 및 기관 보안 승인 전까지 이 화면을 외부 접근 허가의 근거로
                사용하지 마세요. IP만으로 인증하지 않으며, 기존 운영 인증 미설정 상태는
                계속 차단됩니다.
              </p>
              <div className="meta-grid">
                <div className="meta-card">
                  <div className="label">서비스키 관리</div>
                  <div className="value">{status.external_service.service_client_management_available ? "사용 가능" : "미구현"}</div>
                </div>
                <div className="meta-card">
                  <div className="label">서비스 호출자 인증</div>
                  <div className="value">{status.external_service.managed_service_authentication_available ? "사용 가능" : "미구현"}</div>
                </div>
              </div>
              <div className="dd-action-row">
                <button type="button" className="dd-secondary-btn"
                  onClick={() => setShowPolicyDrafts((value) => !value)}>
                  {showPolicyDrafts ? "정책 초안 관리 닫기" : "정책 초안 관리 열기"}
                </button>
              </div>
              {showPolicyDrafts && <ServiceClientDraftsPanel />}
            </section>
          </>
        )}
      </section>
    </main>
  );
}
