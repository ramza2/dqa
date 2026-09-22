import { CatalogApiError, type ApiErrorBody } from "../types/catalog";

const DEFAULT_API_BASE = "/api/v1";

export function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (!configured) {
    return DEFAULT_API_BASE;
  }
  return configured.replace(/\/$/, "");
}

function buildUrl(path: string, query?: Record<string, string | number | boolean | undefined | null>): string {
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
    method: "GET",
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}
