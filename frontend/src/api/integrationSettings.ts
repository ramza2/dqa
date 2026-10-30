import { apiGet, apiPost } from "./client";

export interface IntegrationSettingsStatus {
  llm: {
    provider: "openai_compatible";
    endpoint_configured: boolean;
    model_configured: boolean;
    model: string | null;
    api_key_present: boolean;
    raw_request_egress_allowed: boolean;
    connection_test_available: boolean;
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

/** Explicit admin action; server only tests its own pinned URL and model. */
export interface LLMConnectionTestResult {
  status: "CONNECTED" | "MODEL_NOT_FOUND" | "HTTP_ERROR" | "TIMEOUT" |
    "NETWORK_ERROR" | "INVALID_RESPONSE";
  http_status: number | null;
}

export function testConfiguredLLMConnection(): Promise<LLMConnectionTestResult> {
  return apiPost<Record<string, never>, LLMConnectionTestResult>(
    "/admin/integration-settings/llm/test", {},
  );
}
