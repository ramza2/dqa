import { apiGet, apiPatch, apiPost } from "./client";
import type {
  ConnectionProfile,
  ConnectionProfileCreate,
  ConnectionProfileDiagnostics,
  ConnectionProfileList,
  ConnectionProfileUpdate, OracleMockCapability, OracleMockConnectionTest,
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

// M1: Only the backend-pinned synthetic Mock endpoints are exposed by the UI.
// The unrestricted /enable and /test-connection routes remain uncalled.
export function getOracleMockCapability(): Promise<OracleMockCapability> {
  return apiGet<OracleMockCapability>(`${ROOT}/oracle-mock-capability`);
}

export function ensureOracleMockProfile(): Promise<ConnectionProfile> {
  return apiPost<null, ConnectionProfile>(`${ROOT}/oracle-mock-profile`, null);
}

export function testOracleMockProfile(id: number): Promise<OracleMockConnectionTest> {
  return apiPost<null, OracleMockConnectionTest>(`${ROOT}/${id}/oracle-mock-test`, null);
}

export function enableOracleMockProfile(id: number): Promise<ConnectionProfile> {
  return apiPost<null, ConnectionProfile>(`${ROOT}/${id}/oracle-mock-enable`, null);
}
