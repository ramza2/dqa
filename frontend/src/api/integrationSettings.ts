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
    candidate_review_available: boolean;
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

/** M5-L1D: optional admin action; stateless review, no remote provider call or settings write. */
export type LLMConnectionEnvironment = "modelops" | "snuh_ai" | "self_hosted" | "other";
export type LLMConnectionProtocol = "openai_compatible" | "custom_api";

export interface LLMConnectionCandidatePayload {
  name: string;
  environment: LLMConnectionEnvironment;
  protocol: LLMConnectionProtocol;
  baseUrl: string;
  modelId: string;
  timeoutSeconds: number;
}

export type LLMConnectionCandidateDecisionCode =
  | "INVALID_FIELDS"
  | "INSECURE_ENDPOINT"
  | "INVALID_ENDPOINT"
  | "UNSUPPORTED_ADAPTER"
  | "ENDPOINT_NOT_ALLOWLISTED"
  | "POLICY_REVIEW_REQUIRED";

export interface LLMConnectionCandidateDecision {
  code: LLMConnectionCandidateDecisionCode;
  server_configuration_changed: false;
  credential_loaded: false;
  ready_for_runtime: false;
  ready_for_connection_test: false;
}

/** Call only after a deliberate admin action and a true server capability flag. */
export function reviewLLMConnectionCandidate(
  candidate: LLMConnectionCandidatePayload,
): Promise<LLMConnectionCandidateDecision> {
  return apiPost<LLMConnectionCandidatePayload, LLMConnectionCandidateDecision>(
    "/admin/integration-settings/llm-candidate/review", candidate,
  );
}
