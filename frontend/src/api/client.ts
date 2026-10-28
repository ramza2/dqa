import { CatalogApiError, type ApiErrorBody } from "../types/catalog";

const DEFAULT_API_BASE = "/api/v1";

const DEV_IDENTITY_HEADER_ACTOR = "X-DQA-Dev-Actor";
const DEV_IDENTITY_HEADER_ROLES = "X-DQA-Dev-Roles";

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (!configured) {
    return DEFAULT_API_BASE;
  }
  return configured.replace(/\/$/, "");
}

/** Build optional local-dev identity headers. Production builds never send them. */
export function resolveDevAuthHeaders(env: {
  DEV: boolean;
  VITE_DQA_DEV_ACTOR?: string;
  VITE_DQA_DEV_ROLES?: string;
}): Record<string, string> {
  if (!env.DEV) {
    return {};
  }
  const actor = env.VITE_DQA_DEV_ACTOR?.trim();
  const roles = env.VITE_DQA_DEV_ROLES?.trim();
  const headers: Record<string, string> = {};
  if (actor) {
    headers[DEV_IDENTITY_HEADER_ACTOR] = actor;
  }
  if (roles) {
    headers[DEV_IDENTITY_HEADER_ROLES] = roles;
  }
  return headers;
}

/**
 * Merge request headers and enforce production stripping of X-DQA-Dev-* identity
 * headers even when callers supply them via RequestInit.
 */
export function finalizeRequestHeaders(
  init: RequestInit | undefined,
  options: {
    DEV: boolean;
    jsonBody?: boolean;
    VITE_DQA_DEV_ACTOR?: string;
    VITE_DQA_DEV_ROLES?: string;
  },
): Headers {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (options.jsonBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  if (!options.DEV) {
    headers.delete(DEV_IDENTITY_HEADER_ACTOR);
    headers.delete(DEV_IDENTITY_HEADER_ROLES);
    return headers;
  }

  const auth = resolveDevAuthHeaders({
    DEV: true,
    VITE_DQA_DEV_ACTOR: options.VITE_DQA_DEV_ACTOR,
    VITE_DQA_DEV_ROLES: options.VITE_DQA_DEV_ROLES,
  });
  for (const [key, value] of Object.entries(auth)) {
    if (!headers.has(key)) {
      headers.set(key, value);
    }
  }
  return headers;
}

function mergeRequestHeaders(init?: RequestInit, jsonBody?: boolean): Headers {
  return finalizeRequestHeaders(init, {
    DEV: import.meta.env.DEV,
    jsonBody,
    VITE_DQA_DEV_ACTOR: import.meta.env.VITE_DQA_DEV_ACTOR,
    VITE_DQA_DEV_ROLES: import.meta.env.VITE_DQA_DEV_ROLES,
  });
}

function buildUrl(
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
): string {
  const base = getApiBaseUrl();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = new URL(`${base}${normalizedPath}`, window.location.origin);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") {
        continue;
      }
      url.searchParams.set(key, String(value));
    }
  }
  return `${url.pathname}${url.search}`;
}

async function parseError(response: Response): Promise<CatalogApiError> {
  let message = `Request failed with status ${response.status}`;
  let code: string | null = null;
  try {
    const body = (await response.json()) as { detail?: ApiErrorBody | string } | ApiErrorBody;
    if ("detail" in body) {
      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (body.detail && typeof body.detail === "object") {
        code = body.detail.code ?? null;
        message = body.detail.message ?? message;
      }
    } else if ("message" in body && typeof body.message === "string") {
      code = body.code ?? null;
      message = body.message;
    }
  } catch {
    // Keep status-based message when body is not JSON.
  }
  return new CatalogApiError(response.status, message, code);
}

export async function apiGet<T>(
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(buildUrl(path, query), {
    ...init,
    method: "GET",
    headers: mergeRequestHeaders(init),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

/** Authenticated binary GET using the same request/error boundary as apiGet. */
export async function apiGetDocx(
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
  init?: RequestInit,
): Promise<Blob> {
  const response = await fetch(buildUrl(path, query), {
    ...init,
    method: "GET",
    headers: mergeRequestHeaders(init),
  });
  if (!response.ok) throw await parseError(response);
  const media = response.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase();
  if (media !== "application/vnd.openxmlformats-officedocument.wordprocessingml.document") {
    throw new Error("Unexpected report content type");
  }
  const body = await response.blob();
  if (body.size < 4 || body.size > 3_000_000) {
    throw new Error("Invalid report size");
  }
  return body;
}

export interface SchemaZipResponse {
  blob: Blob;
  totalTables: number;
  nextOffset: number | null;
}

/** Same authentication and sanitized errors; schema reports are limited to 10 MB. */
export async function apiGetSchemaZip(
  path: string,
  query?: Record<string, string | number | boolean | undefined | null>,
  init?: RequestInit,
): Promise<SchemaZipResponse> {
  const response = await fetch(buildUrl(path, query), {
    ...init,
    method: "GET",
    headers: mergeRequestHeaders(init),
  });
  if (!response.ok) throw await parseError(response);
  const mime = response.headers.get("Content-Type")?.split(";")[0].trim().toLowerCase();
  if (mime !== "application/zip") {
    throw new Error("Unexpected schema archive content type");
  }
  const totalHeader = response.headers.get("X-DQA-Schema-Total-Tables");
  const nextHeader = response.headers.get("X-DQA-Schema-Next-Offset");
  if (!totalHeader || !/^[0-9]+$/.test(totalHeader) || !nextHeader
      || !/^(?:-1|[0-9]+)$/.test(nextHeader)) {
    throw new Error("Unverifiable schema archive paging metadata");
  }
  const totalTables = Number(totalHeader);
  const parsedNext = Number(nextHeader);
  if (!Number.isSafeInteger(totalTables) || totalTables < 1
      || !Number.isSafeInteger(parsedNext)
      || (parsedNext !== -1 && (parsedNext < 1 || parsedNext >= totalTables))) {
    throw new Error("Invalid schema archive paging metadata");
  }
  const blob = await response.blob();
  if (blob.size < 4 || blob.size > 10_000_000) {
    throw new Error("Invalid schema archive size");
  }
  return { blob, totalTables, nextOffset: parsedNext === -1 ? null : parsedNext };
}

export async function apiPost<TRequest, TResponse>(
  path: string,
  body: TRequest,
  init?: RequestInit,
): Promise<TResponse> {
  const response = await fetch(buildUrl(path), {
    ...init,
    method: "POST",
    headers: mergeRequestHeaders(init, true),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as TResponse;
}

/** Standard JSON PATCH using the same auth/error boundary as other API helpers. */
export async function apiPatch<TRequest, TResponse>(
  path: string,
  body: TRequest,
  init?: RequestInit,
): Promise<TResponse> {
  const response = await fetch(buildUrl(path), {
    ...init,
    method: "PATCH",
    headers: mergeRequestHeaders(init, true),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as TResponse;
}
