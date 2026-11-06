import { useEffect, useState } from "react";
import {
  getConnectionProfile, getConnectionProfileDiagnostics, listConnectionProfiles,
} from "../api/connectionProfiles";
import type {
  ConnectionProfile, ConnectionProfileDiagnostics, ConnectionProfileList,
} from "../types/connectionProfile";
import { CatalogApiError } from "../types/catalog";
import { InspectorTargetReviewPanel } from "./InspectorTargetReviewPanel";
import { MockInspectorPanel } from "./MockInspectorPanel";

const PAGE_SIZE = 20;

/** Never expose backend error bodies: they can contain connection details. */
function preflightReadError(error: unknown, scope: "목록" | "상세"): string {
  if (error instanceof CatalogApiError) {
    if (error.status === 403) {
      return "DB 분석 사전점검은 연결 프로필 관리 권한이 필요합니다. 현재 권한으로는 Target을 조회할 수 없습니다. 승인된 관리자 계정으로 접근하세요.";
    }
    if (error.status === 401) {
      return "인증 정보가 확인되지 않았습니다. 인증 상태를 확인한 뒤 다시 시도하세요.";
    }
    if (error.status === 503) {
      return "인증 서비스가 준비되지 않았습니다. DQA 관리자에게 서버 인증 설정 확인을 요청하세요.";
    }
  }
  return `DB Target ${scope} 정보를 불러오지 못했습니다. 서버 연결 상태를 확인한 뒤 다시 시도하세요.`;
}

/**
 * Analyzer-inspired, read-only preflight workspace. The existing DQA backend
 * does not issue an independent DBA Preflight verdict. This UI cannot create
 * one and never invokes an Inspector scan, schema-discovery POST or capture.
 */
export function DBAnalysisPreflight() {
  const [page, setPage] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [list, setList] = useState<ConnectionProfileList | null>(null);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [profile, setProfile] = useState<ConnectionProfile | null>(null);
  const [diagnostics, setDiagnostics] = useState<ConnectionProfileDiagnostics | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setListLoading(true);
    setList(null);
    setListError(null);
    void listConnectionProfiles({ limit: PAGE_SIZE, offset: page * PAGE_SIZE })
      .then((response) => {
        if (!active) return;
        if (!Array.isArray(response.items) || !Number.isSafeInteger(response.total) ||
            response.total < 0 || response.limit !== PAGE_SIZE ||
            response.offset !== page * PAGE_SIZE) {
          setListError("대상 목록의 응답 범위를 확인할 수 없습니다.");
          return;
        }
        setList(response);
      })
      .catch((error: unknown) => { if (active) setListError(preflightReadError(error, "목록")); })
      .finally(() => { if (active) setListLoading(false); });
    return () => { active = false; };
  }, [page, refresh]);

  useEffect(() => {
    if (selectedId === null) {
      setProfile(null);
      setDiagnostics(null);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    let active = true;
    setProfile(null);
    setDiagnostics(null);
    setDetailError(null);
    setDetailLoading(true);
    void Promise.all([
      getConnectionProfile(selectedId),
      getConnectionProfileDiagnostics(selectedId),
    ]).then(([detail, status]) => {
      if (!active) return;
      if (detail.id !== selectedId || status.profile_id !== selectedId ||
          detail.source_name !== status.source_name ||
          detail.environment !== status.environment ||
          detail.enabled !== status.enabled || status.live_connection_tested !== false) {
        setDetailError("대상과 설정 진단 정보가 일치하지 않습니다. 다시 선택하세요.");
        return;
      }
      setProfile(detail);
      setDiagnostics(status);
    }).catch((error: unknown) => {
      if (active) setDetailError(preflightReadError(error, "상세"));
    }).finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; };
  }, [selectedId, refresh]);

  function changePage(nextPage: number) {
    setSelectedId(null);
    setPage(nextPage);
  }

  function reload() {
    setSelectedId(null);
    setRefresh((value) => value + 1);
  }

  const isMock = profile?.source_name === "oracle_demis_mock" &&
    profile.environment === "development";

  return (
    <main className="dd-panel preflight-workspace" data-testid="db-analysis-preflight">
      <header className="dd-panel-header">
        <h2>DB Analysis Preflight · DB 분석 사전점검</h2>
        <span className="dd-guidance">대상 설정 확인 · 분석 실행 전 단계</span>
      </header>
      <p className="banner banner-warn" data-testid="preflight-not-authority">
        이 화면은 DB 접속 및 시스템 메타데이터 분석에 앞서 설정 상태만 확인합니다.
        독립 DBA Preflight, 군·보안 승인, 실제 DEMIS 연결 및 Catalog READY 자격을
        판정하지 않습니다. 운영 DB의 분석 실행은 승인된 별도 절차가 필요합니다.
      </p>

      <section className="preflight-section" aria-label="대상 DB 선택">
        <div className="preflight-section-heading">
          <h3>1. 점검할 DB Target 선택</h3>
          <button className="dd-secondary-btn" type="button" onClick={reload}>
            목록 새로고침
          </button>
        </div>
        <div className="preflight-selector-row">
          <label className="dd-field">
            <span>등록된 Connection Profile</span>
            <select aria-label="Preflight DB Target" value={selectedId ?? ""}
              disabled={listLoading || list === null || list.items.length === 0}
              onChange={(event) => setSelectedId(event.target.value ? Number(event.target.value) : null)}>
              <option value="">점검할 Target 선택</option>
              {list?.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} / {item.source_name} / {item.environment}
                </option>
              ))}
            </select>
          </label>
          <div className="preflight-pagination">
            <button type="button" className="dd-secondary-btn"
              disabled={listLoading || page === 0} onClick={() => changePage(page - 1)}>이전</button>
            <span>{page + 1} 페이지 · 총 {list?.total ?? "—"}건</span>
            <button type="button" className="dd-secondary-btn"
              disabled={listLoading || !list || (page + 1) * PAGE_SIZE >= list.total}
              onClick={() => changePage(page + 1)}>다음</button>
          </div>
        </div>
        {listLoading ? <p role="status">DB Target 목록을 조회하는 중…</p> : null}
        {listError ? <p role="alert" className="banner banner-error">{listError}</p> : null}
        {!listLoading && list?.items.length === 0 ? (
          <p className="banner banner-empty">이 페이지에 등록된 Target이 없습니다. DB 연결 관리에서 등록하세요.</p>
        ) : null}
      </section>

      {selectedId !== null ? (
        <section className="preflight-section" aria-label="Target 설정 진단">
          <h3>2. Target 설정 진단 (실접속 없음)</h3>
          {detailLoading ? <p role="status">선택한 Target의 설정을 확인하는 중…</p> : null}
          {detailError ? <p role="alert" className="banner banner-error">{detailError}</p> : null}
          {profile && diagnostics && !detailLoading ? (
            <>
              <div className="status-grid preflight-metadata-grid">
                <div className="status-item"><span className="label">Source</span><span className="value">{profile.source_name}</span></div>
                <div className="status-item"><span className="label">Environment</span><span className="value">{profile.environment}</span></div>
                <div className="status-item"><span className="label">DBMS</span><span className="value">{profile.dbms_type || "미설정"}</span></div>
                <div className="status-item"><span className="label">Database / Service</span><span className="value">{profile.database_name || "미설정"}</span></div>
                <div className="status-item"><span className="label">설정 진단</span>
                  <span className="value">{diagnostics.status === "INCOMPLETE" ? "설정 미완료" :
                    diagnostics.enabled ? "설정 완료 · 프로필 활성" : "설정 완료 · 프로필 비활성"}</span></div>
                <div className="status-item"><span className="label">Credential 참조</span>
                  <span className="value">{diagnostics.credential_reference_configured ? "서버 설정 존재 (값 비표시)" : "미설정"}</span></div>
              </div>
              {diagnostics.issues.length > 0 ? (
                <div className="banner banner-warn">
                  설정 보완 필요: {diagnostics.issues.map((issue) => {
                    if (issue.code === "CREDENTIAL_REFERENCE_MISSING") return "자격증명 참조";
                    if (issue.code === "TARGET_METADATA_INCOMPLETE") return "Target 메타데이터";
                    return "기타 설정";
                  }).join(", ")}
                </div>
              ) : null}
              <p className="dd-guidance">설정 완료 또는 프로필 활성은 실제 연결 성공·메타데이터 권한·독립 DBA 승인과 무관합니다.</p>
            </>
          ) : null}
        </section>
      ) : (
        <p className="banner banner-empty">대상을 선택하면 설정 진단과 허용된 개발용 점검 기능을 확인할 수 있습니다.</p>
      )}

      {profile && diagnostics && !detailLoading ? (
        <>
          <section className="preflight-section" aria-label="Inspector 설정 대조">
            <h3>3. Inspector 대상 설정 대조</h3>
            <InspectorTargetReviewPanel key={profile.id} profileId={profile.id} />
          </section>
          <section className="preflight-section" aria-label="분석 가능 범위">
            <h3>4. 허용된 분석 범위</h3>
            {isMock ? (
              <>
                <p className="dd-guidance">
                  개발용 Oracle Mock만 서버가 지정한 Schema의 분석 조건을 확인할 수 있습니다.
                  Target에서 임의 Schema를 선택하거나 운영 Preflight를 실행할 수 없습니다.
                </p>
                <MockInspectorPanel key={profile.id} profile={profile} readinessOnly />
              </>
            ) : (
              <p className="banner banner-warn" data-testid="preflight-real-target-blocked">
                이 Target의 실제 DB 연결 시험, Schema 목록 조회, 메타데이터 분석은 이 화면에서 제공하지 않습니다.
                독립 DBA·군 보안 승인과 서버 측 허용 정책이 마련되기 전까지 분석 실행이 차단됩니다.
              </p>
            )}
          </section>
          <section className="preflight-section" aria-label="후속 승인 단계">
            <h3>5. 독립 DBA Preflight 및 승인</h3>
            <p className="banner banner-warn">
              미검증 · 승인 대기 — 개발용 Mock 연계 조건이 충족되어도 운영 권한·DBA 증빙·Catalog 활성화는 부여되지 않습니다.
            </p>
          </section>
        </>
      ) : null}
    </main>
  );
}
