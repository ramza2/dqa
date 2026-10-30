import { apiGet, apiPatch, apiPost } from "./client";

const ROOT = "/admin/service-clients";

export type ClientEnvironment = "development" | "test" | "production";
export type ClientDraftStatus = "DRAFT" | "REVOKED";

export interface ServiceClientDraft {
  id: number;
  client_id: string;
  service_name: string;
  organization: string;
  owner_contact: string;
  purpose: string;
  environment: ClientEnvironment;
  requested_scopes: string[];
  proposed_ip_cidrs: string[];
  status: ClientDraftStatus;
  created_by: string;
  updated_by: string;
  created_at: string;
  updated_at: string;
  revoked_at: string | null;
  authentication_enabled: false;
  external_access_allowed: false;
}

export interface ServiceClientDraftList {
  total: number;
  items: ServiceClientDraft[];
}

export interface ServiceClientDraftCreate {
  client_id: string;
  service_name: string;
  organization: string;
  owner_contact: string;
  purpose: string;
  environment: ClientEnvironment;
  requested_scopes: string[];
  proposed_ip_cidrs: string[];
}

export type ServiceClientDraftPatch = Partial<
  Pick<ServiceClientDraftCreate,
    "service_name" | "organization" | "owner_contact" | "purpose" |
    "requested_scopes" | "proposed_ip_cidrs">
>;

export interface ServiceClientDraftEvent {
  id: number;
  action: "CREATED" | "UPDATED" | "REVOKED";
  actor_id: string;
  changed_fields: string[];
  policy_sha256: string;
  occurred_at: string;
}

/** Admin-only draft inventory; these records never authenticate service calls. */
export function listServiceClientDrafts(limit = 25, offset = 0): Promise<ServiceClientDraftList> {
  return apiGet<ServiceClientDraftList>(ROOT, { limit, offset });
}

export function getServiceClientDraft(id: number): Promise<ServiceClientDraft> {
  return apiGet<ServiceClientDraft>(ROOT + "/" + id);
}

export function createServiceClientDraft(
  body: ServiceClientDraftCreate,
): Promise<ServiceClientDraft> {
  return apiPost<ServiceClientDraftCreate, ServiceClientDraft>(ROOT, body);
}

export function patchServiceClientDraft(
  id: number, body: ServiceClientDraftPatch,
): Promise<ServiceClientDraft> {
  return apiPatch<ServiceClientDraftPatch, ServiceClientDraft>(ROOT + "/" + id, body);
}

export function revokeServiceClientDraft(id: number): Promise<ServiceClientDraft> {
  return apiPost<null, ServiceClientDraft>(ROOT + "/" + id + "/revoke", null);
}

export function listServiceClientDraftEvents(id: number): Promise<ServiceClientDraftEvent[]> {
  return apiGet<ServiceClientDraftEvent[]>(ROOT + "/" + id + "/events");
}
