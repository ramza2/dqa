import { useCallback, useEffect, useRef, useState } from "react";
import { listActiveCatalogs } from "../api/catalog";
import {
  getDataDiscoveryIndexStatus,
  rebuildDataDiscoveryDocuments,
  syncDataDiscoveryEmbeddings,
} from "../api/dataDiscovery";
import type { LoadState } from "../hooks/useCatalogExplorer";
import type { CatalogActiveSummary } from "../types/catalog";
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

export function DataDiscoveryIndexStatus() {
  const [sources, setSources] = useState<CatalogActiveSummary[]>([]);
  const [sourcesState, setSourcesState] = useState<LoadState>({
    status: "loading",
    message: null,
    code: null,
    httpStatus: null,
  });
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [active, setActive] = useState<CatalogActiveSummary | null>(null);
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

  useEffect(() => {
    activeRef.current = active;
  }, [active]);
  useEffect(() => {
    selectedSourceRef.current = selectedSource;
  }, [selectedSource]);

  const clearActionUi = useCallback(() => {
    setActionError(null);
    setActionMessage(null);
  }, []);

  const refreshSources = useCallback(async () => {
    setSourcesState({
      status: "loading",
      message: null,
      code: null,
      httpStatus: null,
    });
    try {
      const items = await listActiveCatalogs();
      setSources(items);
      if (items.length === 0) {
        setSourcesState({
          status: "empty",
          message: null,
          code: null,
          httpStatus: null,
        });
        setSelectedSource(null);
        setActive(null);
        setStatus(null);
        return;
      }
      setSourcesState({
        status: "ready",
        message: null,
        code: null,
        httpStatus: null,
      });
      setSelectedSource((prev) => {
        if (prev && items.some((s) => s.source_name === prev)) {
          return prev;
        }
        return items[0].source_name;
      });
    } catch (error) {
      setSources([]);
      setSelectedSource(null);
      setActive(null);
      setStatus(null);
      clearActionUi();
      setSourcesState(toErrorState(error));
    }
  }, [clearActionUi]);

  const loadStatus = useCallback(
    async (sourceName: string, snapshot: CatalogActiveSummary) => {
      const seq = ++requestSeq.current;
      setStatusState({
        status: "loading",
        message: null,
        code: null,
        httpStatus: null,
      });
      setStaleWarning(null);
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
    void refreshSources();
  }, [refreshSources]);

  useEffect(() => {
    if (!selectedSource) {
      setActive(null);
      setStatus(null);
      return;
    }
    const match = sources.find((s) => s.source_name === selectedSource) ?? null;
    setActive(match);
    if (match) {
      void loadStatus(selectedSource, match);
    }
  }, [selectedSource, sources, loadStatus]);

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
        `Rebuilt ${result.document_count} documents (upserted ${result.upserted_count}, deleted ${result.deleted_count}).`,
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
      "This sends derived schema metadata to the configured embedding service. Continue?",
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
        `Synced embeddings: embedded ${result.embedded_count}, skipped ${result.skipped_count}.`,
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
        <h2>Index Status</h2>
        <span className="subtitle">Discovery documents and embedding coverage</span>
      </div>

      <SourceSelector
        sources={sources}
        selectedSource={selectedSource ?? ""}
        onSelect={(name) => {
          requestSeq.current += 1;
          actionSeq.current += 1;
          setSelectedSource(name);
          setStatus(null);
          setStatusState(idleState);
          setStaleWarning(null);
          clearActionUi();
          setBusyAction(null);
        }}
        disabled={sourcesState.status === "loading" || busyAction !== null}
      />

      {sourcesState.status === "loading" ||
      sourcesState.status === "error" ||
      sourcesState.status === "empty" ? (
        <StatusBanner state={sourcesState} emptyLabel="No active Catalog" />
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
          Loading index status…
        </div>
      ) : null}
      {statusState.status === "error" ? (
        <div className="banner banner-error" data-testid="index-status-error">
          {statusState.message}
        </div>
      ) : null}

      {status ? (
        <div className="dd-index-body" data-testid="index-status-body">
          <section className="dd-index-section">
            <h3>Active Catalog</h3>
            <div className="status-grid dd-meta-grid">
              <div className="status-item">
                <span className="label">Source</span>
                <span className="value">{status.source_name}</span>
              </div>
              <div className="status-item">
                <span className="label">Revision</span>
                <span className="value">{status.catalog_revision_id}</span>
              </div>
              <div className="status-item">
                <span className="label">Fingerprint</span>
                <span className="value">{shortenFingerprint(status.schema_fingerprint)}</span>
              </div>
            </div>
          </section>

          <section className="dd-index-section">
            <h3>Discovery Documents</h3>
            <div className="status-grid dd-meta-grid">
              <div className="status-item">
                <span className="label">State</span>
                <span className={stateBadgeClass(status.document_state)} data-testid="document-state">
                  {status.document_state}
                </span>
              </div>
              <div className="status-item">
                <span className="label">Document count</span>
                <span className="value" data-testid="document-count">
                  {status.document_count}
                </span>
              </div>
            </div>
            {status.document_state === "NOT_READY" ? (
              <p className="dd-guidance" data-testid="doc-guidance">
                Build discovery documents before searching.
              </p>
            ) : null}
          </section>

          <section className="dd-index-section">
            <h3>Embedding</h3>
            <div className="status-grid dd-meta-grid">
              <div className="status-item">
                <span className="label">State</span>
                <span
                  className={stateBadgeClass(status.embedding_state)}
                  data-testid="embedding-state"
                >
                  {status.embedding_state}
                </span>
              </div>
              <div className="status-item">
                <span className="label">Provider</span>
                <span className="value">{status.provider ?? "—"}</span>
              </div>
              <div className="status-item">
                <span className="label">Model</span>
                <span className="value">{status.model_name ?? "—"}</span>
              </div>
              <div className="status-item">
                <span className="label">Model revision</span>
                <span className="value">{status.model_revision ?? "—"}</span>
              </div>
              <div className="status-item">
                <span className="label">Model key</span>
                <span className="value">{shortenModelKey(status.model_key)}</span>
              </div>
              <div className="status-item">
                <span className="label">Dimension</span>
                <span className="value">{status.dimension ?? "—"}</span>
              </div>
              <div className="status-item">
                <span className="label">Normalized</span>
                <span className="value">
                  {status.normalized === null || status.normalized === undefined
                    ? "—"
                    : String(status.normalized)}
                </span>
              </div>
            </div>
            {status.embedding_state === "NOT_CONFIGURED" ? (
              <p className="dd-guidance" data-testid="emb-guidance">
                Keyword search is available. Semantic/Hybrid requires an embedding provider.
              </p>
            ) : null}
            {status.embedding_state === "NOT_READY" ? (
              <p className="dd-guidance" data-testid="emb-guidance">
                Keyword search is available. Sync embeddings for Semantic/Hybrid search.
              </p>
            ) : null}
            {status.embedding_state === "CONFIGURATION_ERROR" ? (
              <p className="dd-guidance" data-testid="emb-guidance">
                Embedding configuration is invalid. Keyword search is available; check the server
                embedding settings.
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
              <h3>Coverage</h3>
              <div className="status-grid dd-meta-grid" data-testid="coverage-counts">
                <div className="status-item">
                  <span className="label">Documents</span>
                  <span className="value">{status.coverage.document_count}</span>
                </div>
                <div className="status-item">
                  <span className="label">Embeddings</span>
                  <span className="value">{status.coverage.embedding_count}</span>
                </div>
                <div className="status-item">
                  <span className="label">Current</span>
                  <span className="value">{status.coverage.current_count}</span>
                </div>
                <div className="status-item">
                  <span className="label">Stale</span>
                  <span className="value">{status.coverage.stale_count}</span>
                </div>
                <div className="status-item">
                  <span className="label">Missing</span>
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
              {busyAction === "rebuild" ? "Rebuilding…" : "Rebuild Documents"}
            </button>
            <button
              type="button"
              className="dd-secondary-btn"
              onClick={() => void onSync()}
              disabled={syncDisabled}
              data-testid="sync-embeddings"
            >
              {busyAction === "sync" ? "Syncing…" : "Sync Embeddings"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
