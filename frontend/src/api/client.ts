import { CatalogApiError, type ApiErrorBody } from "../types/catalog";

const DEFAULT_API_BASE = "/api/v1";

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
    headers["X-DQA-Dev-Actor"] = actor;
  }
  if (roles) {
    headers["X-DQA-Dev-Roles"] = roles;
  }
  return headers;
}

function buildDevAuthHeaders(): Record<string, string> {
  return resolveDevAuthHeaders({
    DEV: import.meta.env.DEV,
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

function mergeRequestHeaders(init?: RequestInit, jsonBody?: boolean): Headers {
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  if (jsonBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const auth = buildDevAuthHeaders();
  for (const [key, value] of Object.entries(auth)) {
    if (!headers.has(key)) {
      headers.set(key, value);
    }
  }
  return headers;
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
