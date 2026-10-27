import { useEffect, useRef, useState } from "react";
import type { ConnectionProfile } from "../types/connectionProfile";
import {
  captureSelectedMock, checkMockInspectorReadiness, inspectSelectedMock,
  type MockInspectionSummary, type MockInspectorReadiness, type MockSnapshotSummary,
} from "../api/mockInspector";

type Props = { profile: ConnectionProfile };

const ERROR_LABELS: Record<string, string> = {
  MOCK_INSPECTOR_DISABLED: "개발용 Mock Inspector 기능 비활성",
  MOCK_PROFILE_NOT_FOUND: "선택한 프로필 없음",
  MOCK_PROFILE_MISMATCH: "허용된 Oracle Mock 대상이 아님",
  MOCK_PROFILE_INACTIVE: "프로필 비활성: 연결 검사 후 활성화 필요",
  INSPECTOR_DISABLED: "별도 Inspector 설정 비활성",
  INSPECTOR_ENV_NOT_ALLOWED: "현재 환경에서 Inspector 실행 불가",
  INSPECTOR_NOT_CONFIGURED: "Inspector 메타데이터 전용 계정/스키마 설정 필요",
  MOCK_INSPECTOR_TARGET_MISMATCH: "선택한 Mock과 Inspector 서버 대상 불일치",
  MOCK_INSPECTOR_ACCOUNT_NOT_SEPARATE: "읽기용 계정과 별도 Inspector 계정 필요",
};

export function MockInspectorPanel({ profile }: Props) {
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [readiness, setReadiness] = useState<MockInspectorReadiness | null>(null);
  const [summary, setSummary] = useState<MockInspectionSummary | null>(null);
  const [snapshot, setSnapshot] = useState<MockSnapshotSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const active = useRef(false);

  useEffect(() => {
    active.current = true;
    return () => { active.current = false; seq.current += 1; };
  }, []);

  useEffect(() => {
    seq.current += 1;
    setReadiness(null);
    setSummary(null);
    setSnapshot(null);
    setError(null);
  }, [
    profile.id, profile.source_name, profile.environment, profile.enabled,
    profile.host, profile.port, profile.database_name, profile.username,
    profile.credential_secret_ref,
  ]);

  if (profile.source_name !== "oracle_demis_mock" ||
      profile.environment !== "development") return null;

  async function check(): Promise<void> {
    if (checking || busy) return;
    const token = ++seq.current;
    setChecking(true);
    setError(null);
    setReadiness(null);
    setSummary(null);
    setSnapshot(null);
    try {
      const result = await checkMockInspectorReadiness(profile.id);
      if (!active.current || token !== seq.current) return;
      if (result.profile_id !== profile.id || result.live_connection_tested !== false ||
          result.site_approved !== false || result.catalog_activated !== false ||
          typeof result.ready !== "boolean" ||
          (result.ready && (!result.schema_name ||
            result.reason_code !== "READY_FOR_DEV_INSPECTION"))) {
        setError("Inspector 응답의 안전 조건을 확인할 수 없습니다.");
        return;
      }
      setReadiness(result);
    } catch {
      if (active.current && token === seq.current) setError("Inspector 연계 조건 조회에 실패했습니다.");
    } finally {
      if (active.current && token === seq.current) setChecking(false);
    }
  }

  async function inspect(): Promise<void> {
    if (!readiness?.ready || checking || busy) return;
    const token = ++seq.current;
    setBusy(true);
    setError(null);
    setSummary(null);
    setSnapshot(null);
    try {
      const result = await inspectSelectedMock(profile.id);
      if (!active.current || token !== seq.current) return;
      if (result.source_name !== "oracle_demis_mock" ||
          result.schema_name !== readiness.schema_name ||
          result.imported !== false || result.activated !== false) {
        setError("스키마 분석 응답 대상이 일치하지 않습니다.");
        return;
      }
      setSummary(result);
    } catch {
      if (active.current && token === seq.current) {
        setReadiness(null);
        setError("스키마 분석에 실패했습니다. 별도 Inspector 계정 및 서버 설정을 확인하세요.");
      }
    } finally {
      if (active.current && token === seq.current) setBusy(false);
    }
  }

  async function capture(): Promise<void> {
    if (!readiness?.ready || !summary || checking || busy) return;
    if (!window.confirm("읽기 전용 메타데이터를 다시 수집해 Snapshot 이력에 저장할까요? Catalog는 활성화되지 않습니다.")) return;
    const token = ++seq.current;
    setBusy(true);
    setError(null);
    setSnapshot(null);
    try {
      const result = await captureSelectedMock(profile.id);
      if (!active.current || token !== seq.current) return;
      if (result.source_name !== "oracle_demis_mock" ||
          result.schema_name !== readiness.schema_name ||
          result.imported !== false || result.activated !== false) {
        setError("Snapshot 저장 응답이 현재 대상과 일치하지 않습니다.");
        return;
      }
      setSnapshot(result);
      setSummary(null);
    } catch {
      if (active.current && token === seq.current) {
        setReadiness(null);
        setSummary(null);
        setError("Snapshot 저장에 실패했습니다. 선행 Revision, 권한, 설정을 다시 확인하세요.");
      }
    } finally {
      if (active.current && token === seq.current) setBusy(false);
    }
  }

  return (
    <section className="cp-editor" aria-label="Oracle Mock Schema Inspector">
      <h4>Schema Inspector · Oracle Mock (개발 전용)</h4>
      <p className="dd-guidance">
        연결 조건 확인은 DB에 접속하지 않습니다. 분석·Snapshot 저장은 서버에 별도로
        구성된 메타데이터 전용 계정으로 Oracle 사전정보(ALL_*)만 조회합니다.
        실제 DEMIS 승인이나 Catalog 활성화를 의미하지 않습니다.
      </p>
      <div className="dd-action-row">
        <button type="button" className="dd-secondary-btn"
          disabled={checking || busy} onClick={() => { void check(); }}>
          {checking ? "확인 중…" : "Inspector 연계 조건 확인 (접속 없음)"}
        </button>
        {readiness?.ready ? (
          <button type="button" className="dd-secondary-btn" disabled={checking || busy}
            onClick={() => { void inspect(); }}>
            {busy ? "처리 중…" : "스키마 메타데이터 분석"}
          </button>
        ) : null}
        {summary && readiness?.ready ? (
          <button type="button" className="dd-primary-btn" disabled={checking || busy}
            onClick={() => { void capture(); }}>
            Snapshot 저장 (별도 확인)
          </button>
        ) : null}
      </div>
      {readiness ? (
        <p role="status" className="dd-guidance">
          {readiness.ready
            ? `개발 분석 조건 충족 · 대상 스키마 ${readiness.schema_name} (기관 승인 아님)`
            : `분석 차단 · ${ERROR_LABELS[readiness.reason_code] ?? "설정 확인 필요"}`}
        </p>
      ) : null}
      {summary ? <p role="status" className="dd-guidance">
        메타데이터 분석 완료 · 테이블 {summary.table_count} · 컬럼 {summary.column_count}
        · PK 컬럼 {summary.primary_key_column_count} · FK {summary.foreign_key_count}
        · 인덱스 {summary.index_count} · 저장 전
      </p> : null}
      {snapshot ? <p role="status" className="dd-guidance">
        Snapshot #{snapshot.id} 저장됨 · 변경 상태 {snapshot.diff_status}
        · Catalog 미반영 · READY 승인/활성화 없음
      </p> : null}
      {error ? <p role="alert" className="banner banner-error">{error}</p> : null}
    </section>
  );
}
