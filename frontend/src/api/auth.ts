import { apiGet, apiPost, setLocalSessionCsrf } from "./client";

export type AuthActor = {
  actor_id: string;
  display_name?: string;
  roles: string[];
  provider: string;
  csrf_token?: string;
};

type AuthCapabilities = { mode: string; login_supported: boolean };
type LoginResult = { authenticated: boolean; csrf_token: string };

export function getAuthCapabilities(): Promise<AuthCapabilities> {
  return apiGet<AuthCapabilities>("/auth/capabilities");
}

export async function getAuthActor(): Promise<AuthActor> {
  const actor = await apiGet<AuthActor>("/auth/me");
  if (actor.provider !== "local_session" || !actor.csrf_token) {
    throw new Error("Unexpected authentication response");
  }
  setLocalSessionCsrf(actor.csrf_token);
  return actor;
}

export async function login(username: string, password: string): Promise<AuthActor> {
  setLocalSessionCsrf(null);
  const result = await apiPost<{ username: string; password: string }, LoginResult>(
    "/auth/login", { username, password },
  );
  if (!result.authenticated || !result.csrf_token) {
    throw new Error("Unexpected login response");
  }
  setLocalSessionCsrf(result.csrf_token);
  return getAuthActor();
}

export async function logout(): Promise<void> {
  try {
    await apiPost<Record<string, never>, { authenticated: boolean }>("/auth/logout", {});
  } finally {
    setLocalSessionCsrf(null);
  }
}
