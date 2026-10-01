import { apiGet, apiPost } from "./client";
import type {
  ExecutionFormResponse,
  ExecutionPreviewRequest,
  ExecutionPreviewResponse,
  ParameterExtractionRequest,
  ParameterExtractionResponse,
  QueryExecutionRequest,
  QueryExecutionResponse,
  TemplateRecommendationRequest,
  TemplateRecommendationResponse,
} from "../types/queryAssistant";

export function recommendTemplates(
  body: TemplateRecommendationRequest,
): Promise<TemplateRecommendationResponse> {
  return apiPost<TemplateRecommendationRequest, TemplateRecommendationResponse>(
    "/query-recommendations",
    body,
  );
}

export function getExecutionForm(params: {
  source_name: string;
  template_id: number;
  version_id: number;
}): Promise<ExecutionFormResponse> {
  return apiGet<ExecutionFormResponse>("/query-executions/form", params);
}

export function extractParameters(
  body: ParameterExtractionRequest,
): Promise<ParameterExtractionResponse> {
  return apiPost<ParameterExtractionRequest, ParameterExtractionResponse>(
    "/query-parameters/extract",
    body,
  );
}

export function previewExecution(
  body: ExecutionPreviewRequest,
): Promise<ExecutionPreviewResponse> {
  return apiPost<ExecutionPreviewRequest, ExecutionPreviewResponse>(
    "/query-executions/preview",
    body,
  );
}

export function executeQuery(
  body: QueryExecutionRequest,
): Promise<QueryExecutionResponse> {
  return apiPost<QueryExecutionRequest, QueryExecutionResponse>(
    "/query-executions/execute",
    body,
  );
}
