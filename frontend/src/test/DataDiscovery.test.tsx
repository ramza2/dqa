import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { DataDiscoveryPortal } from "../components/DataDiscoveryPortal";
import { SchemaSearch } from "../components/SchemaSearch";
import { DataDiscoveryIndexStatus } from "../components/DataDiscoveryIndexStatus";
import type {
  DataDiscoveryIndexStatusResponse,
  DataDiscoverySearchResponse,
} from "../types/dataDiscovery";
import {
  activeSource,
  defaultCatalogHandlers,
  installFetchMock,
  jsonResponse,
} from "./mocks";

type FetchHandler = (
  url: URL,
  init?: RequestInit,
) => Response | null | Promise<Response | null>;

afterEach(() => {
  vi.restoreAllMocks();
});

const searchResponse: DataDiscoverySearchResponse = {
  source_name: "oracle_demis_mock",
  catalog_revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  mode: "keyword",
  model_key: null,
  original_query: "glucose",
  normalized_query: "glucose",
  expanded_query: "glucose blood sugar",
  matched_concepts: ["glucose"],
  expanded_terms: ["blood sugar"],
  results: [
    {
      rank: 1,
      identity: {
        source_name: "oracle_demis_mock",
        catalog_revision_id: 1,
        schema_fingerprint: activeSource.schema_fingerprint,
        schema_name: "DEMIS_OWNER",
        table_name: "TB_LAB_RESULT",
        column_name: "GLUCOSE",
      },
      document_key: "table:DEMIS_OWNER.TB_LAB_RESULT.GLUCOSE",
      object_type: "COLUMN",
      keyword_score: 12.5,
      keyword_rank: 1,
      semantic_score: null,
      semantic_rank: null,
      rrf_score: null,
      evidence: ["column_name", "column_comment"],
      evidence_snippet: "blood glucose value",
    },
  ],
  related_tables: [
    {
      schema_name: "DEMIS_OWNER",
      table_name: "TB_ADM_HIST",
      hop_distance: 1,
      seed_schema: "DEMIS_OWNER",
      seed_table: "TB_LAB_RESULT",
      path: [
        {
          from_schema: "DEMIS_OWNER",
          from_table: "TB_ADM_HIST",
          to_schema: "DEMIS_OWNER",
          to_table: "TB_LAB_RESULT",
          constraint_name: "FK_ADM_LAB",
          direction: "outbound",
          from_columns: ["LAB_ID"],
          to_columns: ["GLUCOSE"],
        },
      ],
    },
  ],
  timings: { keyword_ms: 3.2, semantic_ms: 0, total_ms: 4.1 },
};

const indexReady: DataDiscoveryIndexStatusResponse = {
  source_name: "oracle_demis_mock",
  catalog_revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  document_count: 10,
  document_state: "READY",
  embedding_state: "READY",
  provider: "openai_compatible",
  model_name: "stub-model",
  model_revision: "test",
  model_key: "a".repeat(64),
  dimension: 1024,
  normalized: true,
  coverage: {
    document_count: 10,
    embedding_count: 10,
    current_count: 10,
    stale_count: 0,
    missing_count: 0,
  },
  embedding_error_code: null,
};

const indexNotConfigured: DataDiscoveryIndexStatusResponse = {
  ...indexReady,
  embedding_state: "NOT_CONFIGURED",
  provider: null,
  model_name: null,
  model_revision: null,
  model_key: null,
  dimension: null,
  normalized: null,
  coverage: null,
};

function discoveryHandlers(options?: {
  search?: (body: Record<string, unknown>) => Response | Promise<Response>;
  status?: () => Response | Promise<Response>;
  rebuild?: () => Response | Promise<Response>;
  sync?: () => Response | Promise<Response>;
}): FetchHandler[] {
  const handlers: FetchHandler[] = [
    (url, init) => {
      if (url.pathname !== "/api/v1/data-discovery/search" || (init?.method ?? "GET") !== "POST") {
        return null;
      }
      const body = JSON.parse(String(init?.body ?? "{}")) as Record<string, unknown>;
      if (options?.search) {
        return options.search(body);
      }
      return jsonResponse(searchResponse);
    },
    (url) => {
      if (!url.pathname.match(/^\/api\/v1\/data-discovery\/[^/]+\/index-status$/)) {
        return null;
      }
      if (options?.status) {
        return options.status();
      }
      return jsonResponse(indexNotConfigured);
    },
    (url, init) => {
      if (
        !url.pathname.match(/^\/api\/v1\/data-discovery\/[^/]+\/documents\/rebuild$/) ||
        (init?.method ?? "GET") !== "POST"
      ) {
        return null;
      }
      if (options?.rebuild) {
        return options.rebuild();
      }
      return jsonResponse({
        source_name: "oracle_demis_mock",
        catalog_revision_id: 1,
        schema_fingerprint: activeSource.schema_fingerprint,
        document_count: 10,
        upserted_count: 10,
        deleted_count: 0,
        builder_version: "1",
      });
    },
    (url, init) => {
      if (
        !url.pathname.match(/^\/api\/v1\/data-discovery\/[^/]+\/embeddings\/sync$/) ||
        (init?.method ?? "GET") !== "POST"
      ) {
        return null;
      }
      if (options?.sync) {
        return options.sync();
      }
      return jsonResponse({
        source_name: "oracle_demis_mock",
        catalog_revision_id: 1,
        schema_fingerprint: activeSource.schema_fingerprint,
        model_key: "a".repeat(64),
        document_count: 10,
        embedded_count: 10,
        skipped_count: 0,
        coverage: indexReady.coverage,
      });
    },
    ...defaultCatalogHandlers(),
  ];
  return handlers;
}

describe("App navigation Data Discovery", () => {
  it("keeps Query Assistant and exposes Data Discovery instead of Catalog Explorer", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(discoveryHandlers());
    render(<App />);

    expect(screen.getByTestId("query-assistant")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Catalog Explorer" })).not.toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Data Discovery" })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Data Discovery" }));
    expect(await screen.findByTestId("data-discovery-portal")).toBeInTheDocument();
    expect(screen.getByTestId("schema-search")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Query Assistant" }));
    expect(await screen.findByTestId("query-assistant")).toBeInTheDocument();
    restore();
  });
});

describe("DataDiscoveryPortal tabs", () => {
  it("switches Schema Search, Schema Explorer, and Index Status", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(discoveryHandlers());
    render(<DataDiscoveryPortal />);

    expect(screen.getByTestId("schema-search")).toBeInTheDocument();
    await user.click(screen.getByTestId("dd-tab-explorer"));
    expect(await screen.findByText("DQA / Catalog Explorer")).toBeInTheDocument();
    await user.click(screen.getByTestId("dd-tab-index"));
    expect(await screen.findByTestId("data-discovery-index-status")).toBeInTheDocument();
    await user.click(screen.getByTestId("dd-tab-search"));
    expect(await screen.findByTestId("schema-search")).toBeInTheDocument();
    restore();
  });
});

describe("SchemaSearch", () => {
  it("does not call search until explicit submit and sends correct payload", async () => {
    const user = userEvent.setup();
    let searchCalls = 0;
    let lastBody: Record<string, unknown> | null = null;
    const restore = installFetchMock(
      discoveryHandlers({
        search: (body) => {
          searchCalls += 1;
          lastBody = body;
          return jsonResponse(searchResponse);
        },
      }),
    );
    render(<SchemaSearch />);
    await screen.findByTestId("search-query-input");

    await user.type(screen.getByTestId("search-query-input"), "glucose");
    expect(searchCalls).toBe(0);

    await user.selectOptions(screen.getByTestId("search-mode"), "keyword");
    await user.selectOptions(screen.getByTestId("search-object-type"), "COLUMN");
    await user.click(screen.getByTestId("search-submit"));

    await waitFor(() => expect(searchCalls).toBe(1));
    expect(lastBody).toMatchObject({
      source_name: "oracle_demis_mock",
      query: "glucose",
      mode: "keyword",
      object_type: "COLUMN",
      top_k: 10,
      expand_terms: true,
      expand_relations: true,
      max_relation_hops: 1,
    });
    expect(await screen.findByTestId("search-results")).toBeInTheDocument();
    expect(screen.getByText("TB_LAB_RESULT")).toBeInTheDocument();
    expect(screen.getByText("blood glucose value")).toBeInTheDocument();
    expect(screen.getByTestId("search-terminology")).toHaveTextContent("Matched concepts");
    expect(screen.getByTestId("search-related-tables")).toHaveTextContent(
      "DEMIS_OWNER.TB_ADM_HIST.LAB_ID",
    );
    restore();
  });

  it("shows guidance for discovery/embedding errors", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      discoveryHandlers({
        search: () =>
          jsonResponse(
            {
              detail: {
                code: "DISCOVERY_INDEX_NOT_READY",
                message: "discovery documents are not ready",
              },
            },
            409,
          ),
      }),
    );
    render(<SchemaSearch />);
    await screen.findByTestId("search-query-input");
    await user.type(screen.getByTestId("search-query-input"), "x");
    await user.click(screen.getByTestId("search-submit"));
    expect(await screen.findByTestId("search-error")).toHaveTextContent(
      /rebuild discovery documents/i,
    );
    restore();
  });

  it("shows embedding not configured guidance", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      discoveryHandlers({
        search: () =>
          jsonResponse(
            {
              detail: {
                code: "EMBEDDING_NOT_CONFIGURED",
                message: "embedding provider is not configured",
              },
            },
            503,
          ),
      }),
    );
    render(<SchemaSearch />);
    await screen.findByTestId("search-query-input");
    await user.type(screen.getByTestId("search-query-input"), "x");
    await user.click(screen.getByTestId("search-submit"));
    expect(await screen.findByTestId("search-error")).toHaveTextContent(
      /Keyword search is still available/i,
    );
    restore();
  });

  it("shows embedding not ready guidance", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      discoveryHandlers({
        search: () =>
          jsonResponse(
            {
              detail: {
                code: "EMBEDDING_NOT_READY",
                message: "embeddings are not ready",
              },
            },
            409,
          ),
      }),
    );
    render(<SchemaSearch />);
    await screen.findByTestId("search-query-input");
    await user.type(screen.getByTestId("search-query-input"), "x");
    await user.click(screen.getByTestId("search-submit"));
    expect(await screen.findByTestId("search-error")).toHaveTextContent(/sync embeddings/i);
    restore();
  });

  it("ignores stale search responses when active revision differs", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      discoveryHandlers({
        search: () =>
          jsonResponse({
            ...searchResponse,
            catalog_revision_id: 99,
            schema_fingerprint: "stale-fingerprint-value",
          }),
      }),
    );
    render(<SchemaSearch />);
    await screen.findByTestId("search-query-input");
    await user.type(screen.getByTestId("search-query-input"), "glucose");
    await user.click(screen.getByTestId("search-submit"));
    expect(
      await screen.findByText(/Catalog revision changed\. Please run the search again/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("search-results")).not.toBeInTheDocument();
    restore();
  });
});

describe("DataDiscoveryIndexStatus", () => {
  it("renders READY / NOT_CONFIGURED states and coverage", async () => {
    const restore = installFetchMock(
      discoveryHandlers({
        status: () => jsonResponse(indexReady),
      }),
    );
    render(<DataDiscoveryIndexStatus />);
    expect(await screen.findByTestId("document-state")).toHaveTextContent("READY");
    expect(screen.getByTestId("embedding-state")).toHaveTextContent("READY");
    expect(screen.getByTestId("coverage-counts")).toHaveTextContent("10");
    restore();
  });

  it("shows NOT_CONFIGURED guidance and disables sync", async () => {
    const restore = installFetchMock(discoveryHandlers());
    render(<DataDiscoveryIndexStatus />);
    expect(await screen.findByTestId("embedding-state")).toHaveTextContent("NOT_CONFIGURED");
    expect(screen.getByTestId("emb-guidance")).toHaveTextContent(/Keyword search is available/i);
    expect(screen.getByTestId("sync-embeddings")).toBeDisabled();
    restore();
  });

  it("rebuilds documents and refreshes status", async () => {
    const user = userEvent.setup();
    let rebuildCalls = 0;
    const restore = installFetchMock(
      discoveryHandlers({
        status: () =>
          jsonResponse(
            rebuildCalls === 0
              ? { ...indexNotConfigured, document_count: 0, document_state: "NOT_READY" }
              : { ...indexNotConfigured, document_count: 12, document_state: "READY" },
          ),
        rebuild: () => {
          rebuildCalls += 1;
          return jsonResponse({
            source_name: "oracle_demis_mock",
            catalog_revision_id: 1,
            schema_fingerprint: activeSource.schema_fingerprint,
            document_count: 12,
            upserted_count: 12,
            deleted_count: 0,
            builder_version: "1",
          });
        },
      }),
    );
    render(<DataDiscoveryIndexStatus />);
    expect(await screen.findByTestId("document-state")).toHaveTextContent("NOT_READY");
    await user.click(screen.getByTestId("rebuild-documents"));
    await waitFor(() => expect(rebuildCalls).toBe(1));
    expect(await screen.findByTestId("document-count")).toHaveTextContent("12");
    expect(screen.getByTestId("index-action-message")).toHaveTextContent(/Rebuilt 12 documents/i);
    restore();
  });

  it("requires confirmation for sync and refreshes afterward", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    let syncCalls = 0;
    const restore = installFetchMock(
      discoveryHandlers({
        status: () =>
          jsonResponse(
            syncCalls === 0
              ? {
                  ...indexReady,
                  embedding_state: "NOT_READY",
                  coverage: {
                    document_count: 10,
                    embedding_count: 0,
                    current_count: 0,
                    stale_count: 0,
                    missing_count: 10,
                  },
                }
              : indexReady,
          ),
        sync: () => {
          syncCalls += 1;
          return jsonResponse({
            source_name: "oracle_demis_mock",
            catalog_revision_id: 1,
            schema_fingerprint: activeSource.schema_fingerprint,
            model_key: "a".repeat(64),
            document_count: 10,
            embedded_count: 10,
            skipped_count: 0,
            coverage: indexReady.coverage,
          });
        },
      }),
    );
    render(<DataDiscoveryIndexStatus />);
    expect(await screen.findByTestId("embedding-state")).toHaveTextContent("NOT_READY");
    await user.click(screen.getByTestId("sync-embeddings"));
    expect(confirmSpy).toHaveBeenCalledWith(
      expect.stringMatching(/derived schema metadata/i),
    );
    await waitFor(() => expect(syncCalls).toBe(1));
    expect(await screen.findByTestId("embedding-state")).toHaveTextContent("READY");
    restore();
  });

  it("shows administrator permission message on 403", async () => {
    const user = userEvent.setup();
    const restore = installFetchMock(
      discoveryHandlers({
        status: () => jsonResponse(indexNotConfigured),
        rebuild: () =>
          jsonResponse(
            { detail: { code: "AUTHORIZATION_DENIED", message: "permission denied" } },
            403,
          ),
      }),
    );
    render(<DataDiscoveryIndexStatus />);
    await screen.findByTestId("rebuild-documents");
    await user.click(screen.getByTestId("rebuild-documents"));
    expect(await screen.findByTestId("index-action-error")).toHaveTextContent(
      /Administrator permission is required/i,
    );
    restore();
  });
});
