import { apiGet, apiPatch, apiPost } from "./client";
import type {
  ConnectionProfile,
  ConnectionProfileCreate,
  ConnectionProfileDiagnostics,
  ConnectionProfileList,
  ConnectionProfileUpdate,
} from "../types/connectionProfile";

const ROOT = "/connection-profiles";

export function listConnectionProfiles(filters: {
  source_name?: string;
  environment?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<ConnectionProfileList> {
  return apiGet<ConnectionProfileList>(ROOT, filters);
}

export function getConnectionProfile(id: number): Promise<ConnectionProfile> {
  return apiGet<ConnectionProfile>(`${ROOT}/${id}`);
}

/** Configuration-only endpoint. Never triggers a DEMIS connection. */
export function getConnectionProfileDiagnostics(id: number): Promise<ConnectionProfileDiagnostics> {
  return apiGet<ConnectionProfileDiagnostics>(`${ROOT}/${id}/diagnostics`);
}

export function createConnectionProfile(body: ConnectionProfileCreate): Promise<ConnectionProfile> {
  return apiPost<ConnectionProfileCreate, ConnectionProfile>(ROOT, body);
}

export function updateConnectionProfile(
  id: number, body: ConnectionProfileUpdate,
): Promise<ConnectionProfile> {
  return apiPatch<ConnectionProfileUpdate, ConnectionProfile>(`${ROOT}/${id}`, body);
}

export function disableConnectionProfile(id: number): Promise<ConnectionProfile> {
  return apiPost<null, ConnectionProfile>(`${ROOT}/${id}/disable`, null);
}

// Deliberately no /enable and no /test-connection callers in S-05-C1.
