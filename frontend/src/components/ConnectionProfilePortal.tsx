import { useEffect, useState, type FormEvent } from "react";
import { CatalogApiError } from "../types/catalog";
import type {
  ConnectionProfile, ConnectionProfileCreate, ConnectionProfileDiagnostics,
  ConnectionProfileList, ConnectionProfileUpdate,
} from "../types/connectionProfile";
import {
  createConnectionProfile, disableConnectionProfile, getConnectionProfile,
  getConnectionProfileDiagnostics, listConnectionProfiles, updateConnectionProfile,
} from "../api/connectionProfiles";

type Mode = "view" | "create" | "edit";
type ProfileForm = {
  name: string; source_name: string; environment: string; dbms_type: string;
  host: string; port: string; database_name: string; username: string;
};
type Filters = { source_name: string; environment: string };
const EMPTY: ProfileForm = {
  name: "", source_name: "", environment: "", dbms_type: "",
  host: "", port: "", database_name: "", username: "",
};
const PAGE_SIZE = 20;

function friendlyError(error: unknown): string {
  if (error instanceof CatalogApiError) {
    if (error.status === 403 || error.status === 401) {
      return "Connection Profile 관리 권한이 없습니다. 관리자에게 문의하세요.";
    }
    if (error.status === 404) return "프로필을 찾을 수 없습니다. 목록을 새로고침하세요.";
    if (error.status === 409) return "같은 Source와 Environment의 프로필이 이미 존재합니다.";
    if (error.status === 422) return "입력 형식이 올바르지 않습니다. 값을 확인하세요.";
  }
  return "요청에 실패했습니다. 잠시 후 다시 시도하세요.";
}

function formFromProfile(profile: ConnectionProfile): ProfileForm {
  return {
    name: profile.name,
    source_name: profile.source_name,
    environment: profile.environment,
    dbms_type: profile.dbms_type ?? "",
    host: profile.host ?? "",
    port: profile.port == null ? "" : String(profile.port),
    database_name: profile.database_name ?? "",
    username: profile.username ?? "",
  };
}

function buildCreate(form: ProfileForm): ConnectionProfileCreate | null {
  const name = form.name.trim();
  const source_name = form.source_name.trim();
  const environment = form.environment.trim();
  const port = form.port.trim();
  if (!name || !source_name || !environment) return null;
  if (port && (!/^\d+$/.test(port) || Number(port) < 1 || Number(port) > 65535)) return null;
  return {
    name, source_name, environment,
    dbms_type: form.dbms_type.trim() || null,
    host: form.host.trim() || null,
    port: port ? Number(port) : null,
    database_name: form.database_name.trim() || null,
    username: form.username.trim() || null,
  };
}

function changedFields(form: ProfileForm, original: ConnectionProfile): ConnectionProfileUpdate {
  const requested = buildCreate(form);
  if (!requested) return {};
  const changed: ConnectionProfileUpdate = {};
  const fields = ["name", "dbms_type", "host", "port", "database_name", "username"] as const;
  for (const field of fields) {
    if (requested[field] !== original[field]) {
      // The backend PATCH contract accepts null to clear optional metadata.
      Object.assign(changed, { [field]: requested[field] });
    }
  }
  return changed;
}

function diagnosticsLabel(status: ConnectionProfileDiagnostics["status"]): string {
  if (status === "INCOMPLETE") return "설정 미완료";
  if (status === "CONFIGURED_DISABLED") return "설정 완료 · 비활성";
  return "설정 완료 · 활성";
}

function issueLabel(code: string): string {
  if (code === "CREDENTIAL_REFERENCE_MISSING") return "자격증명 참조 설정 필요";
  if (code === "TARGET_METADATA_INCOMPLETE") return "호스트/포트 메타데이터 확인 필요";
  return "설정 진단 항목 확인 필요";
}

export function ConnectionProfilePortal() {
  const [draftFilters, setDraftFilters] = useState<Filters>({ source_name: "", environment: "" });
  const [filters, setFilters] = useState<Filters>({ source_name: "", environment: "" });
  const [page, setPage] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [list, setList] = useState<ConnectionProfileList | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ConnectionProfile | null>(null);
  const [diagnostics, setDiagnostics] = useState<ConnectionProfileDiagnostics | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>("view");
  const [form, setForm] = useState<ProfileForm>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadingList(true);
    setList(null); // Do not show rows from a previous filter while loading.
    setListError(null);
    void listConnectionProfiles({
      source_name: filters.source_name || undefined,
      environment: filters.environment || undefined,
      limit: PAGE_SIZE, offset: page * PAGE_SIZE,
    }).then((result) => {
      if (active) setList(result);
    }).catch((error: unknown) => {
      if (active) setListError(friendlyError(error));
    }).finally(() => {
      if (active) setLoadingList(false);
    });
    return () => { active = false; };
  }, [filters, page, refresh]);

  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      setDiagnostics(null);
      setDetailError(null);
      setLoadingDetail(false);
      return;
    }
    let active = true;
    setDetail(null);
    setDiagnostics(null);
    setDetailError(null);
    setLoadingDetail(true);
    void Promise.all([
      getConnectionProfile(selectedId),
      getConnectionProfileDiagnostics(selectedId),
    ]).then(([profile, status]) => {
      if (!active) return;
      if (profile.id !== selectedId || status.profile_id !== selectedId ||
          profile.source_name !== status.source_name ||
          profile.environment !== status.environment) {
        setDetailError("응답 정보가 일치하지 않습니다. 다시 조회하세요.");
        return;
      }
      setDetail(profile);
      setDiagnostics(status);
    }).catch((error: unknown) => {
      if (active) setDetailError(friendlyError(error));
    }).finally(() => {
      if (active) setLoadingDetail(false);
    });
    return () => { active = false; };
  }, [selectedId, refresh]);

  function selectProfile(id: number): void {
    if (saving) return;
    setSelectedId(id);
    setMode("view");
    setActionError(null);
    setMessage(null);
  }

  function applyFilters(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (saving) return;
    setSelectedId(null);
    setMode("view");
    setPage(0);
    setFilters({ source_name: draftFilters.source_name.trim(),
                 environment: draftFilters.environment.trim() });
    setMessage(null);
  }

  function openCreate(): void {
    setSelectedId(null);
    setMode("create");
    setForm({ ...EMPTY, source_name: filters.source_name, environment: filters.environment });
    setActionError(null);
    setMessage(null);
  }

  function openEdit(): void {
    if (!detail || detail.enabled) return;
    setForm(formFromProfile(detail));
    setMode("edit");
    setActionError(null);
    setMessage(null);
  }

  function cancelForm(): void {
    setMode("view");
    setActionError(null);
  }

  async function save(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (saving) return;
    const create = buildCreate(form);
    if (!create) {
      setActionError("필수 항목과 포트(1~65535)를 확인하세요.");
      return;
    }
    if (mode === "edit" && (!detail || detail.enabled)) return;
    setSaving(true);
    setActionError(null);
    setMessage(null);
    try {
      const result = mode === "create"
        ? await createConnectionProfile(create)
        : await updateConnectionProfile(detail!.id, changedFields(form, detail!));
      setMode("view");
      setSelectedId(result.id);
      setMessage(mode === "create" ? "비활성 프로필을 등록했습니다." : "프로필 정보를 수정했습니다.");
      setRefresh((value) => value + 1);
    } catch (error) {
      setActionError(friendlyError(error));
    } finally {
      setSaving(false);
    }
  }

  async function disable(): Promise<void> {
    if (!detail?.enabled || saving) return;
    if (!window.confirm(`프로필 "${detail.name}"을 비활성화할까요? 기존 연결을 사용하는 작업에 영향이 있을 수 있습니다.`)) {
      return;
    }
    setSaving(true);
    setActionError(null);
    setMessage(null);
    try {
      await disableConnectionProfile(detail.id);
      setMessage("프로필을 비활성화했습니다.");
      setRefresh((value) => value + 1);
    } catch (error) {
      setActionError(friendlyError(error));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="dd-panel cp-portal" data-testid="connection-profile-portal">
      <header className="dd-panel-header">
        <h2>Connection Profiles</h2>
        <span className="dd-guidance">관리자 설정 정보 · DEMIS 실접속 없음</span>
      </header>
      <p className="banner banner-warn">
        설정 진단은 연결·승인 상태를 증명하지 않습니다. 운영 EMR 직접 접속은 허용되지 않으며,
        군·DBA 승인 전 실제 복제 DB 연결·활성화를 진행하지 마세요.
        이 화면은 연결 테스트, 활성화, 자격증명 입력을 제공하지 않습니다.
      </p>

      <form className="cp-filters dd-form-row" onSubmit={applyFilters}>
        <label className="dd-field">
          <span>Source</span>
          <input aria-label="Profile source filter" value={draftFilters.source_name}
            onChange={(e) => setDraftFilters((f) => ({ ...f, source_name: e.target.value }))} />
        </label>
        <label className="dd-field">
          <span>Environment</span>
          <input aria-label="Profile environment filter" value={draftFilters.environment}
            onChange={(e) => setDraftFilters((f) => ({ ...f, environment: e.target.value }))} />
        </label>
        <div className="dd-action-row cp-filter-actions">
          <button className="dd-primary-btn" type="submit" disabled={saving}>조회</button>
          <button className="dd-secondary-btn" type="button" disabled={saving}
            onClick={() => setRefresh((v) => v + 1)}>새로고침</button>
          <button className="dd-secondary-btn" type="button" disabled={saving} onClick={openCreate}>
            비활성 프로필 등록
          </button>
        </div>
      </form>

      {listError ? <div className="banner banner-error" role="alert">{listError}</div> : null}
      {loadingList ? <p role="status">프로필 목록 조회 중…</p> : null}
      {list && !loadingList ? (
        <section aria-label="Connection Profile 목록">
          <p className="dd-guidance">총 {list.total}건 · {page + 1}페이지</p>
          {list.items.length === 0 ? <p className="banner banner-empty">프로필이 없습니다.</p> : (
            <div className="cp-table-wrap">
              <table className="data-table cp-table">
                <thead><tr><th>이름</th><th>Source</th><th>Environment</th><th>DBMS</th><th>설정 상태</th><th>상세</th></tr></thead>
                <tbody>{list.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.name}</td><td>{item.source_name}</td><td>{item.environment}</td>
                    <td>{item.dbms_type || "—"}</td>
                    <td>{item.enabled ? "활성 (연결 미검증)" : "비활성"}</td>
                    <td><button type="button" className="dd-secondary-btn"
                      aria-label={`상세: ${item.name}`} disabled={saving}
                      onClick={() => selectProfile(item.id)}>상세</button></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
          <div className="dd-action-row">
            <button type="button" className="dd-secondary-btn" disabled={page === 0 || saving}
              onClick={() => { setSelectedId(null); setMode("view"); setPage((v) => Math.max(0, v - 1)); }}>이전</button>
            <button type="button" className="dd-secondary-btn"
              disabled={(page + 1) * PAGE_SIZE >= list.total || saving}
              onClick={() => { setSelectedId(null); setMode("view"); setPage((v) => v + 1); }}>다음</button>
          </div>
        </section>
      ) : null}
      {message ? <p className="banner" role="status">{message}</p> : null}
      {actionError ? <p className="banner banner-error" role="alert">{actionError}</p> : null}

      {mode === "create" || mode === "edit" ? (
        <section className="cp-editor" aria-label={mode === "create" ? "프로필 등록" : "프로필 수정"}>
          <h3>{mode === "create" ? "비활성 프로필 등록" : "프로필 정보 수정"}</h3>
          <p className="dd-guidance">
            Source/Environment는 등록 후 변경할 수 없습니다. 자격증명 참조는 보안 절차에 따라 별도로 관리하세요.
          </p>
          <form onSubmit={(e) => { void save(e); }} className="cp-editor-form">
            {([
              ["name", "이름"], ["source_name", "Source"], ["environment", "Environment"],
              ["dbms_type", "DBMS"], ["host", "Host"], ["port", "Port"],
              ["database_name", "Database"], ["username", "Username"],
            ] as const).map(([key, label]) => (
              <label key={key} className="dd-field">
                <span>{label}{["name", "source_name", "environment"].includes(key) ? " *" : ""}</span>
                <input
                  aria-label={`Profile ${key}`}
                  value={form[key]}
                  maxLength={key === "port" ? 5 : key === "environment" || key === "dbms_type" ? 64 : 255}
                  required={key === "name" || key === "source_name" || key === "environment"}
                  disabled={saving || (mode === "edit" && (key === "source_name" || key === "environment"))}
                  onChange={(e) => setForm((old) => ({ ...old, [key]: e.target.value }))}
                />
              </label>
            ))}
            <div className="dd-action-row cp-form-actions">
              <button type="submit" className="dd-primary-btn" disabled={saving}>
                {saving ? "저장 중…" : "저장"}
              </button>
              <button type="button" className="dd-secondary-btn" disabled={saving} onClick={cancelForm}>취소</button>
            </div>
          </form>
        </section>
      ) : null}

      {mode === "view" && selectedId !== null ? (
        <section className="cp-detail" aria-label="Connection Profile 상세">
          <h3>프로필 상세</h3>
          {loadingDetail ? <p role="status">설정 진단 조회 중…</p> : null}
          {detailError ? <p className="banner banner-error" role="alert">{detailError}</p> : null}
          {detail && diagnostics && !loadingDetail ? (
            <>
              <div className="status-grid">
                <div className="status-item"><span className="label">Name</span><span className="value">{detail.name}</span></div>
                <div className="status-item"><span className="label">Source</span><span className="value">{detail.source_name}</span></div>
                <div className="status-item"><span className="label">Environment</span><span className="value">{detail.environment}</span></div>
                <div className="status-item"><span className="label">DBMS</span><span className="value">{detail.dbms_type || "미설정"}</span></div>
                <div className="status-item"><span className="label">Target host</span><span className="value">{detail.host || "미설정"}</span></div>
                <div className="status-item"><span className="label">Port</span><span className="value">{detail.port ?? "미설정"}</span></div>
                <div className="status-item"><span className="label">Database</span><span className="value">{detail.database_name || "미설정"}</span></div>
                <div className="status-item"><span className="label">User</span><span className="value">{detail.username || "미설정"}</span></div>
                <div className="status-item"><span className="label">Credential reference</span>
                  <span className="value">{diagnostics.credential_reference_configured ? "설정됨 (값 비표시)" : "미설정"}</span></div>
                <div className="status-item"><span className="label">Configuration</span>
                  <span className="value">{diagnosticsLabel(diagnostics.status)}</span></div>
              </div>
              {diagnostics.issues.length ? (
                <ul>{diagnostics.issues.map((issue, i) => <li key={`${issue.code}-${i}`}>{issueLabel(issue.code)}</li>)}</ul>
              ) : null}
              <p className="dd-guidance">실제 DB 접속 검사: 미실행 · 연결 가능 여부 및 승인 여부는 확인되지 않았습니다.</p>
              <div className="dd-action-row">
                <button type="button" className="dd-secondary-btn"
                  disabled={saving || detail.enabled} onClick={openEdit}>
                  정보 수정{detail.enabled ? " (비활성 후 가능)" : ""}
                </button>
                {detail.enabled ? (
                  <button type="button" className="dd-secondary-btn" disabled={saving}
                    onClick={() => { void disable(); }}>비활성화</button>
                ) : null}
              </div>
            </>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
