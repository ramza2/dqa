import { useEffect, useState, type FormEvent } from "react";
import { CatalogApiError } from "../types/catalog";
import {
  createServiceClientDraft,
  getServiceClientDraft,
  listServiceClientDraftEvents,
  listServiceClientDrafts,
  patchServiceClientDraft,
  revokeServiceClientDraft,
  type ClientEnvironment,
  type ServiceClientDraft,
  type ServiceClientDraftCreate,
  type ServiceClientDraftEvent,
  type ServiceClientDraftPatch,
  type ServiceClientDraftList,
} from "../api/serviceClientDrafts";

type EditorMode = "create" | "edit" | null;
type DraftForm = {
  client_id: string;
  service_name: string;
  organization: string;
  owner_contact: string;
  purpose: string;
  environment: ClientEnvironment;
  scopes: string;
  cidrs: string;
};

const PAGE_SIZE = 25;
const EMPTY_FORM: DraftForm = {
  client_id: "", service_name: "", organization: "", owner_contact: "",
  purpose: "", environment: "development", scopes: "", cidrs: "",
};

function fromDraft(draft: ServiceClientDraft): DraftForm {
  return {
    client_id: draft.client_id,
    service_name: draft.service_name,
    organization: draft.organization,
    owner_contact: draft.owner_contact,
    purpose: draft.purpose,
    environment: draft.environment,
    scopes: draft.requested_scopes.join("\n"),
    cidrs: draft.proposed_ip_cidrs.join("\n"),
  };
}

function parseList(value: string): string[] {
  return value.split(/[\n,]/).map((entry) => entry.trim()).filter(Boolean);
}

function payloadFrom(form: DraftForm): ServiceClientDraftCreate | null {
  const payload: ServiceClientDraftCreate = {
    client_id: form.client_id.trim(),
    service_name: form.service_name.trim(),
    organization: form.organization.trim(),
    owner_contact: form.owner_contact.trim(),
    purpose: form.purpose.trim(),
    environment: form.environment,
    requested_scopes: parseList(form.scopes),
    proposed_ip_cidrs: parseList(form.cidrs),
  };
  if (!/^[a-z][a-z0-9._-]{2,63}$/.test(payload.client_id)) return null;
  if (!payload.service_name || payload.service_name.length > 128 ||
      !payload.organization || payload.organization.length > 128 ||
      !payload.owner_contact || payload.owner_contact.length > 128 ||
      !payload.purpose || payload.purpose.length > 255 ||
      payload.requested_scopes.length > 32 || payload.proposed_ip_cidrs.length > 32) {
    return null;
  }
  return payload;
}

function patchFrom(form: DraftForm, original: ServiceClientDraft): ServiceClientDraftPatch {
  const next = payloadFrom(form);
  if (!next) return {};
  const changed: ServiceClientDraftPatch = {};
  const fields = [
    "service_name", "organization", "owner_contact", "purpose",
    "requested_scopes", "proposed_ip_cidrs",
  ] as const;
  for (const field of fields) {
    if (JSON.stringify(next[field]) !== JSON.stringify(original[field])) {
      Object.assign(changed, { [field]: next[field] });
    }
  }
  return changed;
}

function errorMessage(error: unknown): string {
  if (error instanceof CatalogApiError) {
    if (error.status === 401 || error.status === 403) return "서비스 정책 관리 권한이 없습니다.";
    if (error.status === 503) return "서버 인증 제공자가 준비되지 않아 접근이 차단되었습니다.";
    if (error.status === 404) return "정책 초안을 찾을 수 없습니다. 목록을 다시 조회하세요.";
    if (error.status === 409) return "중복된 클라이언트 ID이거나 이미 폐기된 정책입니다.";
    if (error.status === 422) return "필수 항목, scope 중복 또는 IP/CIDR 형식을 확인하세요.";
  }
  return "요청을 완료하지 못했습니다. 잠시 후 다시 시도하세요.";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString("ko-KR");
}

export function ServiceClientDraftsPanel() {
  const [page, setPage] = useState(0);
  const [revision, setRevision] = useState(0);
  const [inventory, setInventory] = useState<ServiceClientDraftList | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ServiceClientDraft | null>(null);
  const [events, setEvents] = useState<ServiceClientDraftEvent[]>([]);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [mode, setMode] = useState<EditorMode>(null);
  const [form, setForm] = useState<DraftForm>(EMPTY_FORM);
  const [busy, setBusy] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadingList(true);
    setInventory(null);
    setListError(null);
    void listServiceClientDrafts(PAGE_SIZE, page * PAGE_SIZE).then((result) => {
      if (active) setInventory(result);
    }).catch((error: unknown) => {
      if (active) setListError(errorMessage(error));
    }).finally(() => {
      if (active) setLoadingList(false);
    });
    return () => { active = false; };
  }, [page, revision]);

  useEffect(() => {
    if (selectedId === null) {
      setDetail(null);
      setEvents([]);
      setDetailError(null);
      setLoadingDetail(false);
      return;
    }
    let active = true;
    setDetail(null);
    setEvents([]);
    setDetailError(null);
    setLoadingDetail(true);
    void Promise.all([
      getServiceClientDraft(selectedId),
      listServiceClientDraftEvents(selectedId),
    ]).then(([record, audit]) => {
      if (!active) return;
      if (record.id !== selectedId) {
        setDetailError("응답 대상이 변경되었습니다. 다시 선택하세요.");
        return;
      }
      setDetail(record);
      setEvents(audit);
    }).catch((error: unknown) => {
      if (active) setDetailError(errorMessage(error));
    }).finally(() => {
      if (active) setLoadingDetail(false);
    });
    return () => { active = false; };
  }, [selectedId, revision]);

  function selectDraft(id: number): void {
    if (busy) return;
    setSelectedId(id);
    setMode(null);
    setConfirmRevoke(false);
    setActionError(null);
    setMessage(null);
  }

  function startCreate(): void {
    if (busy) return;
    setSelectedId(null);
    setDetail(null);
    setForm({ ...EMPTY_FORM });
    setMode("create");
    setConfirmRevoke(false);
    setActionError(null);
    setMessage(null);
  }

  function startEdit(): void {
    if (busy || !detail || detail.status !== "DRAFT" || loadingDetail) return;
    setForm(fromDraft(detail));
    setMode("edit");
    setConfirmRevoke(false);
    setActionError(null);
    setMessage(null);
  }

  function cancelEdit(): void {
    if (busy) return;
    setMode(null);
    setActionError(null);
  }

  function update<K extends keyof DraftForm>(key: K, value: DraftForm[K]): void {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (busy || mode === null) return;
    const payload = payloadFrom(form);
    if (!payload) {
      setActionError("client ID(영문 소문자 시작, 3~64자)와 필수 항목을 확인하세요.");
      return;
    }
    const changes = mode === "edit" && detail ? patchFrom(form, detail) : null;
    if (mode === "edit" && (!detail || detail.status !== "DRAFT")) return;
    if (changes && Object.keys(changes).length === 0) {
      setActionError("변경된 항목이 없습니다.");
      return;
    }
    setBusy(true);
    setActionError(null);
    setMessage(null);
    try {
      let saved: ServiceClientDraft;
      if (mode === "create") {
        saved = await createServiceClientDraft(payload);
      } else if (detail && changes) {
        saved = await patchServiceClientDraft(detail.id, changes);
      } else {
        return;
      }
      if (saved.status !== "DRAFT" || saved.authentication_enabled ||
          saved.external_access_allowed) {
        throw new Error("Unexpected service authorization response");
      }
      setSelectedId(saved.id);
      setMode(null);
      setMessage("정책 초안이 저장되었습니다. 실제 서비스 호출 권한은 부여되지 않았습니다.");
      setRevision((value) => value + 1);
    } catch (error: unknown) {
      setActionError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(): Promise<void> {
    if (busy || !confirmRevoke || !detail || detail.status !== "DRAFT" || mode) return;
    setBusy(true);
    setActionError(null);
    setMessage(null);
    try {
      const result = await revokeServiceClientDraft(detail.id);
      if (result.id !== detail.id || result.status !== "REVOKED") {
        throw new Error("Unexpected policy revoke response");
      }
      setConfirmRevoke(false);
      setMessage("정책 초안을 폐기했습니다. 재활성화할 수 없습니다.");
      setRevision((value) => value + 1);
    } catch (error: unknown) {
      setActionError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="qa-panel" aria-label="서비스 클라이언트 정책 초안">
      <h3>서비스 클라이언트 정책 초안</h3>
      <p className="dd-guidance">
        관리자 검토용 등록 정보입니다. DRAFT/REVOKED 상태만 지원하며 서비스 인증,
        API/MCP 접근, IP 허용 정책은 활성화되지 않습니다. 서비스키·비밀번호·토큰은 입력하지 마세요.
      </p>
      <div className="dd-action-row">
        <button type="button" className="dd-secondary-btn" disabled={busy}
          onClick={() => setRevision((value) => value + 1)}>
          목록 새로고침
        </button>
        <button type="button" className="dd-primary-btn" disabled={busy} onClick={startCreate}>
          정책 초안 등록
        </button>
      </div>
      {loadingList && <p role="status">정책 목록을 불러오는 중입니다.</p>}
      {!loadingList && listError && <p role="alert" className="banner banner-error">{listError}</p>}
      {!loadingList && inventory && (
        <>
          <div className="cp-table-wrap">
            <table className="data-table cp-table">
              <caption className="muted">등록 정책 {inventory.total}건</caption>
              <thead><tr>
                <th scope="col">클라이언트 ID</th>
                <th scope="col">서비스</th>
                <th scope="col">기관</th>
                <th scope="col">환경</th>
                <th scope="col">상태</th>
                <th scope="col">관리</th>
              </tr></thead>
              <tbody>
                {inventory.items.map((item) => (
                  <tr key={item.id}>
                    <td className="mono">{item.client_id}</td>
                    <td>{item.service_name}</td>
                    <td>{item.organization}</td>
                    <td>{item.environment}</td>
                    <td>{item.status === "DRAFT" ? "초안 · 인증 불가" : "폐기 · 인증 불가"}</td>
                    <td>
                      <button type="button" disabled={busy}
                        aria-label={item.client_id + " 상세"}
                        onClick={() => selectDraft(item.id)}>상세</button>
                    </td>
                  </tr>
                ))}
                {inventory.items.length === 0 && (
                  <tr><td colSpan={6}>등록된 서비스 클라이언트 정책 초안이 없습니다.</td></tr>
                )}
              </tbody>
            </table>
          </div>
          <div className="dd-action-row">
            <button type="button" disabled={busy || page === 0}
              onClick={() => { setPage((value) => value - 1); setSelectedId(null); setMode(null); }}>
              이전
            </button>
            <span className="muted">{page + 1}페이지</span>
            <button type="button" disabled={busy || (page + 1) * PAGE_SIZE >= inventory.total}
              onClick={() => { setPage((value) => value + 1); setSelectedId(null); setMode(null); }}>
              다음
            </button>
          </div>
        </>
      )}
      {message && <p role="status" className="banner">{message}</p>}
      {actionError && <p role="alert" className="banner banner-error">{actionError}</p>}
      {mode && (
        <form className="cp-editor" onSubmit={(event) => { void submit(event); }}
          aria-label={mode === "create" ? "정책 초안 등록 양식" : "정책 초안 수정 양식"}>
          <h3>{mode === "create" ? "정책 초안 등록" : "정책 초안 수정"}</h3>
          <div className="cp-editor-form">
            <label className="dd-field">클라이언트 ID
              <input value={form.client_id} disabled={mode === "edit" || busy} maxLength={64}
                onChange={(event) => update("client_id", event.target.value)} required />
            </label>
            <label className="dd-field">서비스명
              <input value={form.service_name} disabled={busy} maxLength={128}
                onChange={(event) => update("service_name", event.target.value)} required />
            </label>
            <label className="dd-field">기관
              <input value={form.organization} disabled={busy} maxLength={128}
                onChange={(event) => update("organization", event.target.value)} required />
            </label>
            <label className="dd-field">담당자 연락처
              <input value={form.owner_contact} disabled={busy} maxLength={128}
                onChange={(event) => update("owner_contact", event.target.value)} required />
            </label>
            <label className="dd-field">환경
              <select value={form.environment} disabled={mode === "edit" || busy}
                onChange={(event) => update("environment", event.target.value as ClientEnvironment)}>
                <option value="development">개발</option>
                <option value="test">시험</option>
                <option value="production">운영 (정책 초안만)</option>
              </select>
            </label>
            <label className="dd-field">목적
              <input value={form.purpose} disabled={busy} maxLength={255}
                onChange={(event) => update("purpose", event.target.value)} required />
            </label>
            <label className="dd-field">요청 scope (한 줄에 하나)
              <textarea value={form.scopes} disabled={busy} rows={3}
                onChange={(event) => update("scopes", event.target.value)} />
            </label>
            <label className="dd-field">제안 IP/CIDR (한 줄에 하나)
              <textarea value={form.cidrs} disabled={busy} rows={3}
                onChange={(event) => update("cidrs", event.target.value)} />
            </label>
          </div>
          <p className="muted">
            scope/CIDR은 요청안이며 실제 접근 정책에 적용되지 않습니다.
            전체 공개 CIDR(0.0.0.0/0, ::/0)은 허용하지 않습니다.
          </p>
          <div className="dd-action-row">
            <button className="dd-primary-btn" type="submit" disabled={busy}>
              {busy ? "저장 중" : "초안 저장"}
            </button>
            <button className="dd-secondary-btn" type="button" disabled={busy} onClick={cancelEdit}>
              취소
            </button>
          </div>
        </form>
      )}
      {selectedId !== null && mode === null && (
        <section className="cp-detail" aria-label="정책 상세">
          <h3>정책 상세 및 감사</h3>
          {loadingDetail && <p role="status">상세 및 감사 이력을 불러오는 중입니다.</p>}
          {!loadingDetail && detailError && (
            <p role="alert" className="banner banner-error">{detailError}</p>
          )}
          {!loadingDetail && detail && (
            <>
              <div className="meta-grid">
                <div className="meta-card"><div className="label">클라이언트 ID</div>
                  <div className="value">{detail.client_id}</div></div>
                <div className="meta-card"><div className="label">상태</div>
                  <div className="value">{detail.status} · 인증 불가</div></div>
                <div className="meta-card"><div className="label">담당자</div>
                  <div className="value">{detail.owner_contact}</div></div>
                <div className="meta-card"><div className="label">목적</div>
                  <div className="value">{detail.purpose}</div></div>
                <div className="meta-card"><div className="label">요청 scope</div>
                  <div className="value">{detail.requested_scopes.join(", ") || "없음"}</div></div>
                <div className="meta-card"><div className="label">제안 IP/CIDR</div>
                  <div className="value">{detail.proposed_ip_cidrs.join(", ") || "없음"}</div></div>
              </div>
              {detail.status === "DRAFT" && (
                <div className="dd-action-row">
                  <button type="button" className="dd-secondary-btn" disabled={busy} onClick={startEdit}>
                    초안 수정
                  </button>
                  <label className="dd-check">
                    <input type="checkbox" disabled={busy} checked={confirmRevoke}
                      onChange={(event) => setConfirmRevoke(event.target.checked)} />
                    영구 폐기를 확인합니다
                  </label>
                  <button type="button" disabled={!confirmRevoke || busy} onClick={() => { void revoke(); }}>
                    정책 초안 폐기
                  </button>
                </div>
              )}
              {detail.status === "REVOKED" && (
                <p className="muted">폐기된 정책은 수정하거나 다시 활성화할 수 없습니다.</p>
              )}
              <section aria-label="변경 감사 이력">
                <h4>변경 감사 이력</h4>
                <div className="cp-table-wrap">
                  <table className="data-table">
                    <thead><tr><th>일시</th><th>작업</th><th>수행자</th><th>변경 필드</th></tr></thead>
                    <tbody>
                      {events.map((entry) => (
                        <tr key={entry.id}>
                          <td>{formatDate(entry.occurred_at)}</td>
                          <td>{entry.action}</td>
                          <td>{entry.actor_id}</td>
                          <td>{entry.changed_fields.join(", ") || "-"}</td>
                        </tr>
                      ))}
                      {events.length === 0 && <tr><td colSpan={4}>감사 이력이 없습니다.</td></tr>}
                    </tbody>
                  </table>
                </div>
              </section>
            </>
          )}
        </section>
      )}
    </section>
  );
}
