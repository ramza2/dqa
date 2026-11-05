import { useCallback, useEffect, useRef, useState } from "react";
import { listActiveCatalogs } from "../api/catalog";
import {
  getDataDiscoveryIndexStatus,
  rebuildDataDiscoveryDocuments,
  syncDataDiscoveryEmbeddings,
} from "../api/dataDiscovery";
import type { LoadState } from "../hooks/useCatalogExplorer";
import type { CatalogActiveSummary } from "../types/catalog";
import { useOptionalCatalogSource } from "../hooks/catalogSourceContext";
import { CatalogApiError } from "../types/catalog";
import type {
  DataDiscoveryEmbeddingSyncResponse,
  DataDiscoveryIndexStatusResponse,
  DataDiscoveryRebuildResponse,
} from "../types/dataDiscovery";
import {
  STALE_ACTION_MESSAGE,
  STALE_STATUS_MESSAGE,
  formatDiscoveryError,
  shortenFingerprint,
  shortenModelKey,
} from "../utils/dataDiscovery";
import { SourceSelector } from "./ActiveCatalogHeader";
import { StatusBanner } from "./StatusBanner";

const idleState: LoadState = {
  status: "idle",
  message: null,
  code: null,
  httpStatus: null,
};

type ActionSnapshot = {
  source_name: string;
  revision_id: number;
  schema_fingerprint: string;
  token: number;
};

function toErrorState(error: unknown): LoadState {
  if (error instanceof CatalogApiError) {
    return {
      status: "error",
      message: formatDiscoveryError(error),
      code: error.code,
      httpStatus: error.status,
    };
  }
  return {
    status: "error",
    message: formatDiscoveryError(error),
    code: null,
    httpStatus: null,
  };
}

function stateBadgeClass(state: string): string {
  switch (state) {
    case "READY":
      return "badge badge-ready";
    case "NOT_CONFIGURED":
      return "badge badge-muted";
    case "CONFIGURATION_ERROR":
      return "badge badge-error";
    default:
      return "badge badge-warn";
  }
}

function actionStillCurrent(
  snapshot: ActionSnapshot,
  actionSeq: number,
  selectedSource: string | null,
): boolean {
  return snapshot.token === actionSeq && selectedSource === snapshot.source_name;
}

function responseMatchesSnapshot(
  snapshot: ActionSnapshot,
  response: {
    source_name: string;
    catalog_revision_id: number;
    schema_fingerprint: string;
  },
  active: CatalogActiveSummary | null,
): boolean {
  if (
    !active ||
    active.source_name !== snapshot.source_name ||
    active.revision_id !== snapshot.revision_id ||
    active.schema_fingerprint !== snapshot.schema_fingerprint
  ) {
    return false;
  }
  return (
    response.source_name === snapshot.source_name &&
    response.catalog_revision_id === snapshot.revision_id &&
    response.schema_fingerprint === snapshot.schema_fingerprint
  );
}

export function DataDiscoveryIndexStatus({
  sharedSourceBar = false,
  onBusyChange,
}: { sharedSourceBar?: boolean; onBusyChange?: (busy: boolean) => void } = {}) {
  const sourceSelection = useOptionalCatalogSource();
  const useShared = sharedSourceBar && sourceSelection !== null;
  const [localSources, setLocalSources] = useState<CatalogActiveSummary[]>([]);
  const [localSourcesState, setLocalSourcesState] = useState<LoadState>({
    status: "loading",
    message: null,
    code: null,
    httpStatus: null,
  });
  const [localSelectedSource, setLocalSelectedSource] = useState<string | null>(null);
  const [localActive, setLocalActive] = useState<CatalogActiveSummary | null>(null);
  const sources = useShared ? sourceSelection.sources : localSources;
  const sourcesState = useShared ? sourceSelection.sourcesState : localSourcesState;
  const selectedSource = useShared ? sourceSelection.selectedSource || null : localSelectedSource;
  const active = useShared
    ? sources.find((item) => item.source_name === selectedSource) ?? null
    : localActive;
  const reloadShared = useShared ? sourceSelection.reloadSources : null;
  const [status, setStatus] = useState<DataDiscoveryIndexStatusResponse | null>(null);
  const [statusState, setStatusState] = useState<LoadState>(idleState);
  const [staleWarning, setStaleWarning] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"rebuild" | "sync" | null>(null);

  const requestSeq = useRef(0);
  const actionSeq = useRef(0);
  const activeRef = useRef<CatalogActiveSummary | null>(null);
  const selectedSourceRef = useRef<string | null>(null);

  activeRef.current = active;
  selectedSourceRef.current = selectedSource;

  useEffect(() => {
    onBusyChange?.(busyAction !== null);
    return () => onBusyChange?.(false);
  }, [onBusyChange, busyAction]);

  const clearActionUi = useCallback(() => {
    setActionError(null);
    setActionMessage(null);
  }, []);

  const refreshSources = useCallback(async () => {
    if (reloadShared) {
      await reloadShared();
      return;
    }
    setLocalSourcesState({
      status: "loading",
      message: null,
      code: null,
      httpStatus: null,
    });
    try {
      const items = await listActiveCatalogs();
      setLocalSources(items);
      if (items.length === 0) {
        setLocalSourcesState({
          status: "empty",
          message: null,
          code: null,
          httpStatus: null,
        });
        setLocalSelectedSource(null);
        setLocalActive(null);
        setStatus(null);
        return;
      }
      setLocalSourcesState({
        status: "ready",
        message: null,
        code: null,
        httpStatus: null,
      });
      setLocalSelectedSource((prev) => {
        if (prev && items.some((s) => s.source_name === prev)) {
          return prev;
        }
        return items[0].source_name;
      });
    } catch (error) {
      setLocalSources([]);
      setLocalSelectedSource(null);
      setLocalActive(null);
      setStatus(null);
      clearActionUi();
      setLocalSourcesState(toErrorState(error));
    }
  }, [clearActionUi, reloadShared]);

  const loadStatus = useCallback(
    async (sourceName: string, snapshot: CatalogActiveSummary) => {
      const seq = ++requestSeq.current;
      setStatusState({
        status: "loading",
        message: null,
        code: null,
        httpStatus: null,
      });
      // Preserve a revision-mismatch warning across the automatic status refresh.
      // Only an explicit source switch or a new user action dismisses it.
      try {
        const response = await getDataDiscoveryIndexStatus(sourceName);
        if (seq !== requestSeq.current) {
          return;
        }
        if (selectedSourceRef.current !== sourceName) {
          return;
        }
        const current = activeRef.current;
        if (
          !current ||
          current.source_name !== response.source_name ||
          current.revision_id !== response.catalog_revision_id ||
          current.schema_fingerprint !== response.schema_fingerprint ||
          current.source_name !== snapshot.source_name ||
          current.revision_id !== snapshot.revision_id ||
          current.schema_fingerprint !== snapshot.schema_fingerprint
        ) {
          setStatus(null);
          setStaleWarning(STALE_STATUS_MESSAGE);
          setStatusState(idleState);
          void refreshSources();
          return;
        }
        setStatus(response);
        setStatusState({
          status: "ready",
          message: null,
          code: null,
          httpStatus: null,
        });
      } catch (error) {
        if (seq !== requestSeq.current) {
          return;
        }
        if (selectedSourceRef.current !== sourceName) {
          return;
        }
        setStatus(null);
        setStatusState(toErrorState(error));
      }
    },
    [refreshSources],
  );

  useEffect(() => {
    if (!useShared) void refreshSources();
  }, [useShared, refreshSources]);

  useEffect(() => {
    if (useShared) return;
    if (!selectedSource) {
      setLocalActive(null);
      setStatus(null);
      return;
    }
    const match = sources.find((s) => s.source_name === selectedSource) ?? null;
    setLocalActive(match);
  }, [selectedSource, sources, useShared]);

  useEffect(() => {
    if (!selectedSource || !active || active.source_name !== selectedSource) {
      setStatus(null);
      return;
    }
    void loadStatus(selectedSource, active);
  }, [selectedSource, active, loadStatus]);

  const rejectStaleActionOnCurrentSource = useCallback(() => {
    clearActionUi();
    setStaleWarning(STALE_ACTION_MESSAGE);
    // Only invalidate status loads for the still-selected source.
    requestSeq.current += 1;
    setStatus(null);
    setStatusState(idleState);
    void refreshSources();
  }, [clearActionUi, refreshSources]);

  const onRebuild = async () => {
    if (!selectedSource || !active || busyAction) {
      return;
    }
    const snapshot: ActionSnapshot = {
      source_name: active.source_name,
      revision_id: active.revision_id,
      schema_fingerprint: active.schema_fingerprint,
      token: ++actionSeq.current,
    };
    setBusyAction("rebuild");
    clearActionUi();
    setStaleWarning(null);
    try {
      const result: DataDiscoveryRebuildResponse =
        await rebuildDataDiscoveryDocuments(snapshot.source_name);
      if (!actionStillCurrent(snapshot, actionSeq.current, selectedSourceRef.current)) {
        // Source/action already invalidated; never commit onto the new screen.
        return;
      }
      if (!responseMatchesSnapshot(snapshot, result, activeRef.current)) {
        rejectStaleActionOnCurrentSource();
        return;
      }
      setActionMessage(
        `검색 문서 ${result.document_count}건 재생성 완료 (추가·갱신 ${result.upserted_count}건, 삭제 ${result.deleted_count}건).`,
      );
      const current = activeRef.current;
      if (current && current.source_name === snapshot.source_name) {
        await loadStatus(snapshot.source_name, current);
      }
    } catch (error) {
      if (!actionStillCurrent(snapshot, actionSeq.current, selectedSourceRef.current)) {
        return;
      }
      setActionError(formatDiscoveryError(error));
    } finally {
      if (snapshot.token === actionSeq.current) {
        setBusyAction(null);
      }
    }
  };

  const onSync = async () => {
    if (!selectedSource || !active || busyAction) {
      return;
    }
    const confirmed = window.confirm(
      "검색용 스키마 메타데이터가 설정된 임베딩 서비스로 전송됩니다. 임베딩 동기화를 진행할까요? 실제 환자·진료 데이터는 대상이 아닙니다.",
    );
    if (!confirmed) {
      return;
    }
    const snapshot: ActionSnapshot = {
      source_name: active.source_name,
      revision_id: active.revision_id,
      schema_fingerprint: active.schema_fingerprint,
      token: ++actionSeq.current,
    };
    setBusyAction("sync");
    clearActionUi();
    setStaleWarning(null);
    try {
      const result: DataDiscoveryEmbeddingSyncResponse =
        await syncDataDiscoveryEmbeddings(snapshot.source_name);
      if (!actionStillCurrent(snapshot, actionSeq.current, selectedSourceRef.current)) {
        return;
      }
      if (!responseMatchesSnapshot(snapshot, result, activeRef.current)) {
        rejectStaleActionOnCurrentSource();
        return;
      }
      setActionMessage(
        `임베딩 동기화 완료 (처리 ${result.embedded_count}건, 건너뜀 ${result.skipped_count}건).`,
      );
      const current = activeRef.current;
      if (current && current.source_name === snapshot.source_name) {
        await loadStatus(snapshot.source_name, current);
      }
    } catch (error) {
      if (!actionStillCurrent(snapshot, actionSeq.current, selectedSourceRef.current)) {
        return;
      }
      setActionError(formatDiscoveryError(error));
    } finally {
      if (snapshot.token === actionSeq.current) {
        setBusyAction(null);
      }
    }
  };

  const syncDisabled =
    busyAction !== null ||
    !status ||
    status.document_state !== "READY" ||
    status.embedding_state === "NOT_CONFIGURED" ||
    status.embedding_state === "CONFIGURATION_ERROR";

  return (
    <div className="dd-panel" data-testid="data-discovery-index-status">
      <div className="dd-panel-header">
        <h2>검색 인덱스 상태</h2>
        <span className="subtitle">검색 문서와 임베딩 준비 상태를 확인하고 필요한 경우 갱신합니다.</span>
      </div>

      {!useShared ? <SourceSelector
        sources={sources}
        selectedSource={selectedSource ?? ""}
        onSelect={(name) => {
          requestSeq.current += 1;
          actionSeq.current += 1;
          setLocalSelectedSource(name);
          setStatus(null);
          setStatusState(idleState);
          setStaleWarning(null);
          clearActionUi();
          setBusyAction(null);
        }}
        disabled={sourcesState.status === "loading" || busyAction !== null}
      /> : null}

      {!useShared && (sourcesState.status === "loading" ||
      sourcesState.status === "error" ||
      sourcesState.status === "empty") ? (
        <StatusBanner state={sourcesState} emptyLabel="활성 Catalog가 없습니다." />
      ) : null}

      {staleWarning ? (
        <div className="banner banner-warn" data-testid="index-stale-warning">
          {staleWarning}
        </div>
      ) : null}
      {actionError ? (
        <div className="banner banner-error" data-testid="index-action-error">
          {actionError}
        </div>
      ) : null}
      {actionMessage ? (
        <div className="banner banner-empty" data-testid="index-action-message">
          {actionMessage}
        </div>
      ) : null}

      {statusState.status === "loading" ? (
        <div className="banner banner-empty" data-testid="index-status-loading">
          검색 인덱스 상태를 불러오는 중…
        </div>
      ) : null}
      {statusState.status === "error" ? (
        <div className="banner banner-error" data-testid="index-status-error">
          {statusState.message}
        </div>
      ) : null}

      {status && active && status.source_name === selectedSource &&
      status.catalog_revision_id === active?.revision_id &&
      status.schema_fingerprint === active.schema_fingerprint ? (
        <div className="dd-index-body" data-testid="index-status-body">
          {!useShared ? <section className="dd-index-section">
            <h3>활성 Catalog 정보</h3>
            <div className="status-grid dd-meta-grid">
              <div className="status-item">
                <span className="label">데이터 소스</span>
                <span className="value">{status.source_name}</span>
              </div>
              <div className="status-item">
                <span className="label">개정번호</span>
                <span className="value">{status.catalog_revision_id}</span>
              </div>
              <div className="status-item">
                <span className="label">스키마 지문</span>
                <span className="value">{shortenFingerprint(status.schema_fingerprint)}</span>
              </div>
            </div>
          </section> : null}

          <section className="dd-index-section">
            <h3>검색 문서</h3>
            <div className="status-grid dd-meta-grid">
              <div className="status-item">
                <span className="label">상태</span>
                <span className={stateBadgeClass(status.document_state)} data-testid="document-state">
                  {status.document_state}
                </span>
              </div>
              <div className="status-item">
                <span className="label">문서 수</span>
                <span className="value" data-testid="document-count">
                  {status.document_count}
                </span>
              </div>
            </div>
            {status.document_state === "NOT_READY" ? (
              <p className="dd-guidance" data-testid="doc-guidance">
                검색을 시작하기 전에 검색 문서를 생성해 주세요.
              </p>
            ) : null}
          </section>

          <section className="dd-index-section">
            <h3>의미 검색용 임베딩</h3>
            <div className="status-grid dd-meta-grid">
              <div className="status-item">
                <span className="label">상태</span>
                <span
                  className={stateBadgeClass(status.embedding_state)}
                  data-testid="embedding-state"
                >
                  {status.embedding_state}
                </span>
              </div>
              <div className="status-item">
                <span className="label">제공자</span>
                <span className="value">{status.provider ?? "—"}</span>
              </div>
              <div className="status-item">
                <span className="label">모델</span>
                <span className="value">{status.model_name ?? "—"}</span>
              </div>
              <div className="status-item">
                <span className="label">모델 개정번호</span>
                <span className="value">{status.model_revision ?? "—"}</span>
              </div>
              <div className="status-item">
                <span className="label">모델 식별자</span>
                <span className="value">{shortenModelKey(status.model_key)}</span>
              </div>
              <div className="status-item">
                <span className="label">벡터 차원</span>
                <span className="value">{status.dimension ?? "—"}</span>
              </div>
              <div className="status-item">
                <span className="label">정규화 여부</span>
                <span className="value">
                  {status.normalized === null || status.normalized === undefined
                    ? "—"
                    : status.normalized ? "예" : "아니요"}
                </span>
              </div>
            </div>
            {status.embedding_state === "NOT_CONFIGURED" ? (
              <p className="dd-guidance" data-testid="emb-guidance">
                키워드 검색은 사용할 수 있습니다. 의미 검색과 통합 검색을 사용하려면 임베딩 서비스를 설정해야 합니다.
              </p>
            ) : null}
            {status.embedding_state === "NOT_READY" ? (
              <p className="dd-guidance" data-testid="emb-guidance">
                키워드 검색은 사용할 수 있습니다. 의미 검색과 통합 검색을 사용하려면 임베딩을 동기화해 주세요.
              </p>
            ) : null}
            {status.embedding_state === "CONFIGURATION_ERROR" ? (
              <p className="dd-guidance" data-testid="emb-guidance">
                임베딩 설정에 오류가 있습니다. 키워드 검색은 가능하며 서버의 임베딩 설정을 확인해야 합니다.
                {status.embedding_error_code ? (
                  <>
                    {" "}
                    <code>{status.embedding_error_code}</code>
                  </>
                ) : null}
              </p>
            ) : null}
          </section>

          {status.coverage ? (
            <section className="dd-index-section">
              <h3>인덱싱 처리 현황</h3>
              <div className="status-grid dd-meta-grid" data-testid="coverage-counts">
                <div className="status-item">
                  <span className="label">전체 문서</span>
                  <span className="value">{status.coverage.document_count}</span>
                </div>
                <div className="status-item">
                  <span className="label">전체 임베딩</span>
                  <span className="value">{status.coverage.embedding_count}</span>
                </div>
                <div className="status-item">
                  <span className="label">최신</span>
                  <span className="value">{status.coverage.current_count}</span>
                </div>
                <div className="status-item">
                  <span className="label">갱신 필요</span>
                  <span className="value">{status.coverage.stale_count}</span>
                </div>
                <div className="status-item">
                  <span className="label">미생성</span>
                  <span className="value">{status.coverage.missing_count}</span>
                </div>
              </div>
            </section>
          ) : null}

          <div className="dd-action-row">
            <button
              type="button"
              className="dd-primary-btn"
              onClick={() => void onRebuild()}
              disabled={busyAction !== null}
              data-testid="rebuild-documents"
            >
              {busyAction === "rebuild" ? "문서 재생성 중…" : "검색 문서 재생성"}
            </button>
            <button
              type="button"
              className="dd-secondary-btn"
              onClick={() => void onSync()}
              disabled={syncDisabled}
              data-testid="sync-embeddings"
            >
              {busyAction === "sync" ? "동기화 중…" : "임베딩 동기화"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
