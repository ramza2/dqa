import { useCallback, useEffect, useRef, useState } from "react";
import { listActiveCatalogs } from "../api/catalog";
import { searchDataDiscovery } from "../api/dataDiscovery";
import type { LoadState } from "../hooks/useCatalogExplorer";
import type { CatalogActiveSummary } from "../types/catalog";
import { CatalogApiError } from "../types/catalog";
import type {
  DataDiscoverySearchMode,
  DataDiscoverySearchResponse,
  DiscoveryObjectType,
} from "../types/dataDiscovery";
import {
  STALE_SEARCH_MESSAGE,
  formatDiscoveryError,
  formatRelationPathHop,
  formatScore,
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

export function SchemaSearch() {
  const [sources, setSources] = useState<CatalogActiveSummary[]>([]);
  const [sourcesState, setSourcesState] = useState<LoadState>({
    status: "loading",
    message: null,
    code: null,
    httpStatus: null,
  });
  const [selectedSource, setSelectedSource] = useState<string | null>(null);
  const [active, setActive] = useState<CatalogActiveSummary | null>(null);

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<DataDiscoverySearchMode>("hybrid");
  const [objectType, setObjectType] = useState<"ALL" | DiscoveryObjectType>("ALL");
  const [expandTerms, setExpandTerms] = useState(true);
  const [expandRelations, setExpandRelations] = useState(true);
  const [maxRelationHops, setMaxRelationHops] = useState(1);

  const [searchState, setSearchState] = useState<LoadState>(idleState);
  const [result, setResult] = useState<DataDiscoverySearchResponse | null>(null);
  const [staleWarning, setStaleWarning] = useState<string | null>(null);

  const requestSeq = useRef(0);
  const activeRef = useRef<CatalogActiveSummary | null>(null);
  const selectedSourceRef = useRef<string | null>(null);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);
  useEffect(() => {
    selectedSourceRef.current = selectedSource;
  }, [selectedSource]);

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
      setSourcesState(toErrorState(error));
    }
  }, []);

  useEffect(() => {
    void refreshSources();
  }, [refreshSources]);

  useEffect(() => {
    if (!selectedSource) {
      setActive(null);
      return;
    }
    const match = sources.find((s) => s.source_name === selectedSource) ?? null;
    setActive(match);
  }, [selectedSource, sources]);

  const runSearch = async () => {
    if (!selectedSource || !active || !query.trim()) {
      return;
    }
    const seq = ++requestSeq.current;
    const snapshot = {
      source_name: active.source_name,
      revision_id: active.revision_id,
      schema_fingerprint: active.schema_fingerprint,
    };
    setSearchState({
      status: "loading",
      message: null,
      code: null,
      httpStatus: null,
    });
    setStaleWarning(null);
    setResult(null);
    try {
      const response = await searchDataDiscovery({
        source_name: selectedSource,
        query: query.trim(),
        mode,
        object_type: objectType === "ALL" ? null : objectType,
        top_k: 10,
        expand_terms: expandTerms,
        expand_relations: expandRelations,
        max_relation_hops: expandRelations ? maxRelationHops : 0,
      });
      if (seq !== requestSeq.current) {
        return;
      }
      if (selectedSourceRef.current !== snapshot.source_name) {
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
        setResult(null);
        setStaleWarning(STALE_SEARCH_MESSAGE);
        setSearchState(idleState);
        void refreshSources();
        return;
      }
      setResult(response);
      setSearchState({
        status: "ready",
        message: null,
        code: null,
        httpStatus: null,
      });
    } catch (error) {
      if (seq !== requestSeq.current) {
        return;
      }
      setResult(null);
      setSearchState(toErrorState(error));
    }
  };

  return (
    <div className="dd-panel" data-testid="schema-search">
      <div className="dd-panel-header">
        <h2>Schema Search</h2>
        <span className="subtitle">Keyword / semantic / hybrid catalog search</span>
      </div>

      <SourceSelector
        sources={sources}
        selectedSource={selectedSource ?? ""}
        onSelect={(name) => {
          requestSeq.current += 1;
          setSelectedSource(name);
          setResult(null);
          setStaleWarning(null);
          setSearchState(idleState);
        }}
        disabled={sourcesState.status === "loading"}
      />

      {sourcesState.status === "loading" ||
      sourcesState.status === "error" ||
      sourcesState.status === "empty" ? (
        <StatusBanner state={sourcesState} emptyLabel="No active Catalog" />
      ) : active ? (
        <div className="status-grid dd-meta-grid" data-testid="search-active-meta">
          <div className="status-item">
            <span className="label">Source</span>
            <span className="value">{active.source_name}</span>
          </div>
          <div className="status-item">
            <span className="label">Revision</span>
            <span className="value">{active.revision_id}</span>
          </div>
          <div className="status-item">
            <span className="label">Fingerprint</span>
            <span className="value">{shortenFingerprint(active.schema_fingerprint)}</span>
          </div>
        </div>
      ) : null}

      {staleWarning ? <div className="banner banner-warn">{staleWarning}</div> : null}

      <form
        className="dd-search-form"
        onSubmit={(event) => {
          event.preventDefault();
          void runSearch();
        }}
      >
        <label className="dd-field">
          <span>Query</span>
          <input
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. blood glucose"
            data-testid="search-query-input"
            autoComplete="off"
          />
        </label>

        <div className="dd-form-row">
          <label className="dd-field">
            <span>Search Mode</span>
            <select
              value={mode}
              onChange={(event) => setMode(event.target.value as DataDiscoverySearchMode)}
              data-testid="search-mode"
            >
              <option value="keyword">Keyword</option>
              <option value="semantic">Semantic</option>
              <option value="hybrid">Hybrid</option>
            </select>
          </label>
          <label className="dd-field">
            <span>Object Type</span>
            <select
              value={objectType}
              onChange={(event) =>
                setObjectType(event.target.value as "ALL" | DiscoveryObjectType)
              }
              data-testid="search-object-type"
            >
              <option value="ALL">All</option>
              <option value="TABLE">Table</option>
              <option value="COLUMN">Column</option>
            </select>
          </label>
          <label className="dd-field">
            <span>Relation hops</span>
            <select
              value={maxRelationHops}
              onChange={(event) => setMaxRelationHops(Number(event.target.value))}
              disabled={!expandRelations}
              data-testid="search-relation-hops"
            >
              <option value={1}>1</option>
              <option value={2}>2</option>
            </select>
          </label>
        </div>

        <div className="dd-form-row dd-check-row">
          <label className="dd-check">
            <input
              type="checkbox"
              checked={expandTerms}
              onChange={(event) => setExpandTerms(event.target.checked)}
              data-testid="search-expand-terms"
            />
            Expand medical terms
          </label>
          <label className="dd-check">
            <input
              type="checkbox"
              checked={expandRelations}
              onChange={(event) => setExpandRelations(event.target.checked)}
              data-testid="search-expand-relations"
            />
            Expand relations
          </label>
        </div>

        <button
          type="submit"
          className="dd-primary-btn"
          disabled={!selectedSource || !query.trim() || searchState.status === "loading"}
          data-testid="search-submit"
        >
          {searchState.status === "loading" ? "Searching…" : "Search"}
        </button>
      </form>

      {searchState.status === "error" ? (
        <div className="banner banner-error" data-testid="search-error">
          {searchState.message ?? "Search failed."}
        </div>
      ) : null}

      {result ? (
        <div className="dd-search-results" data-testid="search-results">
          <div className="status-grid dd-meta-grid">
            <div className="status-item">
              <span className="label">Source</span>
              <span className="value">{result.source_name}</span>
            </div>
            <div className="status-item">
              <span className="label">Revision</span>
              <span className="value">{result.catalog_revision_id}</span>
            </div>
            <div className="status-item">
              <span className="label">Fingerprint</span>
              <span className="value">{shortenFingerprint(result.schema_fingerprint)}</span>
            </div>
            <div className="status-item">
              <span className="label">Mode</span>
              <span className="value">{result.mode}</span>
            </div>
            {result.mode !== "keyword" ? (
              <div className="status-item">
                <span className="label">Model key</span>
                <span className="value">{shortenModelKey(result.model_key)}</span>
              </div>
            ) : null}
            <div className="status-item">
              <span className="label">Elapsed</span>
              <span className="value">{result.timings.total_ms.toFixed(1)} ms</span>
            </div>
          </div>

          {(result.matched_concepts.length > 0 || result.expanded_terms.length > 0) && (
            <div className="dd-expansion" data-testid="search-terminology">
              {result.matched_concepts.length > 0 ? (
                <div>
                  <span className="label">Matched concepts</span>
                  <div className="dd-term-list">
                    {result.matched_concepts.map((term) => (
                      <code key={term}>{term}</code>
                    ))}
                  </div>
                </div>
              ) : null}
              {result.expanded_terms.length > 0 ? (
                <div>
                  <span className="label">Expanded terms</span>
                  <div className="dd-term-list">
                    {result.expanded_terms.map((term) => (
                      <code key={term}>{term}</code>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          )}

          <div className="qa-result-table-wrap">
            <table className="data-table" data-testid="search-result-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Type</th>
                  <th>Schema</th>
                  <th>Table</th>
                  <th>Column</th>
                  <th>Kw score</th>
                  <th>Kw rank</th>
                  <th>Sem score</th>
                  <th>Sem rank</th>
                  <th>RRF</th>
                  <th>Evidence</th>
                  <th>Snippet</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((row) => (
                  <tr key={row.document_key}>
                    <td>{row.rank}</td>
                    <td>{row.object_type}</td>
                    <td className="mono">{row.identity.schema_name}</td>
                    <td className="mono">{row.identity.table_name}</td>
                    <td className="mono">{row.identity.column_name ?? "—"}</td>
                    <td className="mono">{formatScore(row.keyword_score)}</td>
                    <td className="mono">{row.keyword_rank ?? "—"}</td>
                    <td className="mono">{formatScore(row.semantic_score)}</td>
                    <td className="mono">{row.semantic_rank ?? "—"}</td>
                    <td className="mono">{formatScore(row.rrf_score)}</td>
                    <td>{row.evidence.join(", ") || "—"}</td>
                    <td className="dd-snippet">{row.evidence_snippet ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {result.related_tables.length > 0 ? (
            <div className="dd-related" data-testid="search-related-tables">
              <h3>Related tables</h3>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Related</th>
                    <th>Seed</th>
                    <th>Hops</th>
                    <th>Path</th>
                  </tr>
                </thead>
                <tbody>
                  {result.related_tables.map((rel) => (
                    <tr
                      key={`${rel.seed_schema}.${rel.seed_table}->${rel.schema_name}.${rel.table_name}:${rel.hop_distance}`}
                    >
                      <td className="mono">
                        {rel.schema_name}.{rel.table_name}
                      </td>
                      <td className="mono">
                        {rel.seed_schema}.{rel.seed_table}
                      </td>
                      <td>{rel.hop_distance}</td>
                      <td>
                        <ul className="dd-path-list">
                          {rel.path.map((hop, index) => (
                            <li key={`${hop.constraint_name ?? "hop"}-${index}`}>
                              <code>{formatRelationPathHop(hop)}</code>
                              <span className="dd-path-meta">
                                {" "}
                                ({hop.direction}
                                {hop.constraint_name ? `, ${hop.constraint_name}` : ""})
                              </span>
                            </li>
                          ))}
                        </ul>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
