import type {
  CatalogActiveSummary,
  CatalogCategoryListResponse,
  CatalogColumnListResponse,
  CatalogIndexListResponse,
  CatalogRelationListResponse,
  CatalogTableDetailResponse,
  CatalogTableListResponse,
} from "../types/catalog";

export const activeSource: CatalogActiveSummary = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint:
    "97ac64035d5d73ab80feb5c99c9875e247d25c375bec61a7672a3c38137c0df0",
  package_version: "2.0",
  package_readiness: "READY",
  activated_at: "2026-09-21T08:15:30+00:00",
};

export const secondSource: CatalogActiveSummary = {
  source_name: "oracle_demis_other",
  revision_id: 7,
  schema_fingerprint: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  package_version: "2.0",
  package_readiness: "READY",
  activated_at: "2026-09-21T09:00:00+00:00",
};

export const tablesResponse: CatalogTableListResponse = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  total: 1,
  limit: 500,
  offset: 0,
  items: [
    {
      schema_name: "DEMIS_OWNER",
      name: "TB_ADM_HIST",
      comment: "환자 입원 이력",
      table_type: "BASE TABLE",
      category_ids: [],
    },
  ],
};

export const tableDetailResponse: CatalogTableDetailResponse = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  item: tablesResponse.items[0],
};

export const columnsResponse: CatalogColumnListResponse = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  total: 2,
  limit: 500,
  offset: 0,
  items: [
    {
      schema_name: "DEMIS_OWNER",
      table_name: "TB_ADM_HIST",
      name: "ADM_ID",
      ordinal: 1,
      data_type: "NUMBER",
      comment: "입원 ID",
      nullable: false,
      is_primary_key: true,
      is_unique: true,
      default: null,
    },
    {
      schema_name: "DEMIS_OWNER",
      table_name: "TB_ADM_HIST",
      name: "WARD_CD",
      ordinal: 2,
      data_type: "VARCHAR2",
      comment: "입원 병동 코드",
      nullable: true,
      is_primary_key: false,
      is_unique: false,
      default: null,
    },
  ],
};

export const outgoingRelations: CatalogRelationListResponse = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  total: 1,
  limit: 500,
  offset: 0,
  items: [
    {
      name: "FK_ADM_ENC",
      schema_name: "DEMIS_OWNER",
      table_name: "TB_ADM_HIST",
      referenced_schema_name: "DEMIS_OWNER",
      referenced_table_name: "TB_ENC_HIST",
      columns: [{ column: "ENC_ID", referenced_column: "ENC_ID" }],
    },
  ],
};

export const incomingRelations: CatalogRelationListResponse = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  total: 1,
  limit: 500,
  offset: 0,
  items: [
    {
      name: "FK_OTHER_TO_ADM",
      schema_name: "DEMIS_OWNER",
      table_name: "TB_OTHER",
      referenced_schema_name: "DEMIS_OWNER",
      referenced_table_name: "TB_ADM_HIST",
      columns: [{ column: "ADM_ID", referenced_column: "ADM_ID" }],
    },
  ],
};

export const indexesResponse: CatalogIndexListResponse = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  total: 1,
  limit: 500,
  offset: 0,
  items: [
    {
      name: "IX_ADM_ENC",
      schema_name: "DEMIS_OWNER",
      table_name: "TB_ADM_HIST",
      unique: false,
      method: "NORMAL",
      columns: ["ENC_ID"],
    },
  ],
};

export const emptyCategories: CatalogCategoryListResponse = {
  source_name: "oracle_demis_mock",
  revision_id: 1,
  schema_fingerprint: activeSource.schema_fingerprint,
  total: 0,
  limit: 500,
  offset: 0,
  items: [],
};

type Handler = (url: URL) => Response | null | Promise<Response | null>;

export function installFetchMock(handlers: Handler[]): () => void {
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url =
      typeof input === "string"
        ? new URL(input, "http://localhost")
        : input instanceof URL
          ? input
          : new URL(input.url, "http://localhost");
    for (const handler of handlers) {
      const result = await handler(url);
      if (result) {
        return result;
      }
    }
    return new Response(JSON.stringify({ detail: { code: "UNHANDLED", message: url.pathname } }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return () => {
    globalThis.fetch = original;
  };
}

export function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export function defaultCatalogHandlers(options?: {
  actives?: CatalogActiveSummary[];
  tables?: CatalogTableListResponse;
  staleTables?: boolean;
}): Handler[] {
  const actives = options?.actives ?? [activeSource];
  const tables = options?.tables ?? tablesResponse;
  return [
    (url) => {
      if (url.pathname === "/api/v1/catalog/active") {
        return jsonResponse(actives);
      }
      return null;
    },
    (url) => {
      const match = url.pathname.match(/^\/api\/v1\/catalog\/active\/([^/]+)$/);
      if (!match) {
        return null;
      }
      const source = decodeURIComponent(match[1]);
      const found = actives.find((item) => item.source_name === source);
      if (!found) {
        return jsonResponse(
          { detail: { code: "CATALOG_ACTIVE_REVISION_NOT_FOUND", message: "missing" } },
          404,
        );
      }
      return jsonResponse(found);
    },
    (url) => {
      if (!(url.pathname.endsWith("/tables") && !url.pathname.includes("/tables/"))) {
        return null;
      }
      if (options?.staleTables) {
        return jsonResponse({
          ...tables,
          revision_id: 999,
          schema_fingerprint: "stale-fingerprint-value-00000000000000000000000000000000",
        });
      }
      return jsonResponse(tables);
    },
    (url) => {
      if (!url.pathname.includes("/tables/DEMIS_OWNER/TB_ADM_HIST")) {
        return null;
      }
      return jsonResponse(tableDetailResponse);
    },
    (url) => {
      if (!url.pathname.endsWith("/columns")) {
        return null;
      }
      return jsonResponse(columnsResponse);
    },
    (url) => {
      if (!url.pathname.endsWith("/relations")) {
        return null;
      }
      if (url.searchParams.get("referenced_table_name")) {
        return jsonResponse(incomingRelations);
      }
      return jsonResponse(outgoingRelations);
    },
    (url) => {
      if (!url.pathname.endsWith("/indexes")) {
        return null;
      }
      return jsonResponse(indexesResponse);
    },
    (url) => {
      if (!url.pathname.endsWith("/categories")) {
        return null;
      }
      return jsonResponse(emptyCategories);
    },
  ];
}
