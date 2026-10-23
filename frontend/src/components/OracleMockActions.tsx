import { useEffect, useRef, useState } from "react";
import {
  enableOracleMockProfile,
  ensureOracleMockProfile,
  getOracleMockCapability,
  testOracleMockProfile,
} from "../api/connectionProfiles";
import type { ConnectionProfile, OracleMockConnectionTest } from "../types/connectionProfile";

interface Props {
  profile: ConnectionProfile | null;
  onSelectProfile: (id: number) => void;
  onRefresh: () => void;
}

function isMockCandidate(profile: ConnectionProfile | null): boolean {
  return profile?.source_name === "oracle_demis_mock" &&
    profile.environment === "development";
}

export function OracleMockActions({ profile, onSelectProfile, onRefresh }: Props) {
  const [available, setAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<OracleMockConnectionTest | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const actionSeq = useRef(0);

  useEffect(() => {
    let active = true;
    void getOracleMockCapability()
      .then((value) => { if (active) setAvailable(value.enabled === true); })
      .catch(() => { if (active) setAvailable(false); });
    return () => { active = false; actionSeq.current += 1; };
  }, []);

  useEffect(() => {
    // A probe result never carries across a changed/selected profile identity.
    actionSeq.current += 1;
    setResult(null);
    setFeedback(null);
    setError(null);
  }, [
    profile?.id, profile?.source_name, profile?.environment, profile?.enabled,
    profile?.host, profile?.port, profile?.database_name,
    profile?.dbms_type, profile?.username,
    profile?.credential_secret_ref,
  ]);

  async function prepare(): Promise<void> {
    if (busy || !available) return;
    const seq = ++actionSeq.current;
    setBusy(true);
    setFeedback(null);
    setError(null);
    try {
      const saved = await ensureOracleMockProfile();
      if (seq !== actionSeq.current) return;
      onSelectProfile(saved.id);
      onRefresh();
      setFeedback("개발용 Oracle Mock 프로필을 준비했습니다. 연결 검사를 실행하세요.");
    } catch {
      if (seq === actionSeq.current) setError("Oracle Mock 프로필을 준비할 수 없습니다. 기존 설정과 개발용 기능 허용 상태를 확인하세요.");
    } finally {
      setBusy(false);
    }
  }

  async function test(): Promise<void> {
    if (busy || !available || !profile || !isMockCandidate(profile)) return;
    const seq = ++actionSeq.current;
    const profileId = profile.id;
    setBusy(true);
    setResult(null);
    setFeedback(null);
    setError(null);
    try {
      const tested = await testOracleMockProfile(profileId);
      if (seq !== actionSeq.current) return;
      if (tested.profile_id !== profileId ||
          tested.source_name !== "oracle_demis_mock" ||
          tested.environment !== "development") {
        setError("연결 검사 응답의 대상이 일치하지 않습니다. 다시 확인하세요.");
        return;
      }
      setResult(tested);
      setFeedback(
        tested.status === "SUCCEEDED" &&
        tested.live_connection_tested === true &&
        tested.reachable === true && tested.read_only === true
          ? "Oracle Mock 읽기 전용 연결 검사 성공 · 아직 프로필 활성화 전입니다."
          : "Oracle Mock 연결 검사 실패. 관리자에게 DB/네트워크/계정 설정 확인을 요청하세요.",
      );
    } catch {
      if (seq === actionSeq.current) setError("연결 검사 요청에 실패했습니다. 대상 설정 및 개발환경 허용 여부를 확인하세요.");
    } finally {
      setBusy(false);
    }
  }

  async function enable(): Promise<void> {
    if (busy || !available || !profile || !isMockCandidate(profile) ||
        profile.enabled || result?.profile_id !== profile.id ||
        result.status !== "SUCCEEDED" || result.live_connection_tested !== true ||
        result.reachable !== true || result.read_only !== true) return;
    if (!window.confirm("Oracle Mock 개발용 프로필을 활성화할까요? 서버에서 읽기 전용 연결을 다시 확인합니다.")) return;
    const seq = ++actionSeq.current;
    setBusy(true);
    setFeedback(null);
    setError(null);
    try {
      const enabled = await enableOracleMockProfile(profile.id);
      if (seq !== actionSeq.current) return;
      if (enabled.id !== profile.id || enabled.enabled !== true ||
          !isMockCandidate(enabled)) {
        setError("활성화 응답이 현재 선택한 Oracle Mock과 일치하지 않습니다.");
        return;
      }
      setResult(null);
      setFeedback("Oracle Mock 프로필을 활성화했습니다. 실제 DEMIS 접근 승인과는 관계없습니다.");
      onRefresh();
    } catch {
      if (seq === actionSeq.current) setError("활성화에 실패했습니다. 서버에서 읽기 전용 연결이 다시 확인되지 않았을 수 있습니다.");
    } finally {
      setBusy(false);
    }
  }

  if (!available) return null;
  const selectedMock = isMockCandidate(profile);
  const successful = result?.profile_id === profile?.id &&
    result?.status === "SUCCEEDED" && result.live_connection_tested === true &&
    result.reachable === true && result.read_only === true;

  return (
    <section className="cp-editor" aria-label="Oracle Mock 개발용 연결">
      <h3>Oracle Mock 연결 · 개발환경 전용</h3>
      <p className="dd-guidance">
        허용된 샘플 DB만 등록·검사할 수 있습니다. 실제 DEMIS 및 운영 복제 DB에는 연결하지 않습니다.
        연결 검사와 프로필 활성화는 별개이며 자격증명 값은 표시하지 않습니다.
      </p>
      <div className="dd-action-row">
        <button type="button" className="dd-secondary-btn"
          disabled={busy} onClick={() => { void prepare(); }}>
          {busy ? "처리 중…" : "Oracle Mock 대상 준비"}
        </button>
        {selectedMock ? (
          <button type="button" className="dd-secondary-btn"
            disabled={busy} onClick={() => { void test(); }}>
            읽기 전용 연결 검사
          </button>
        ) : null}
        {selectedMock && !profile?.enabled ? (
          <button type="button" className="dd-primary-btn"
            disabled={busy || !successful} onClick={() => { void enable(); }}>
            연결 검사 후 활성화
          </button>
        ) : null}
      </div>
      {selectedMock && profile?.enabled ? <p className="dd-guidance">선택된 개발용 프로필은 활성 상태입니다.</p> : null}
      {feedback ? <p role="status" className="banner">{feedback}</p> : null}
      {error ? <p role="alert" className="banner banner-error">{error}</p> : null}
    </section>
  );
}
