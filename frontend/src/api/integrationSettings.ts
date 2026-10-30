import { apiGet } from "./client";

export interface IntegrationSettingsStatus {
  llm: {
    provider: "openai_compatible";
    endpoint_configured: boolean;
    model_configured: boolean;
    model: string | null;
    api_key_present: boolean;
    raw_request_egress_allowed: boolean;
  };
  external_service: {
    service_client_management_available: boolean;
    managed_service_authentication_available: boolean;
  };
  editable: boolean;
}

/** Safe admin status only: no secret, endpoint URL, or mutation support. */
export function getIntegrationSettingsStatus(): Promise<IntegrationSettingsStatus> {
  return apiGet<IntegrationSettingsStatus>("/admin/integration-settings");
}
