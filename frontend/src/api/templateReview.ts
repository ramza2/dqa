import { apiGet, apiPatch, apiPost } from "./client";
import type {
  ReviewTemplateDetail,
  ReviewTemplateList,
  TemplateCreateRequest,
  TemplateNewVersionRequest,
  TemplateReviewEventList,
  TemplateSqlSafetyReview,
  TemplateUpdateRequest,
} from "../types/templateReview";

/** TEMPLATE_READ is enforced by the existing backend. */
export function listReviewTemplates(sourceName: string, offset = 0): Promise<ReviewTemplateList> {
  return apiGet<ReviewTemplateList>("/query-templates", {
    source_name: sourceName.trim() || undefined, limit: 50, offset,
  }, { cache: "no-store" });
}

export function getReviewTemplate(id: number): Promise<ReviewTemplateDetail> {
  return apiGet<ReviewTemplateDetail>(`/query-templates/${id}`, undefined, { cache: "no-store" });
}

export function getReviewTemplateSqlSafety(id: number): Promise<TemplateSqlSafetyReview> {
  return apiGet<TemplateSqlSafetyReview>(
    `/query-templates/${id}/sql-safety`, undefined, { cache: "no-store" },
  );
}

/** AUDIT_READ — may 403 for authors without audit permission. */
export function listReviewEvents(id: number): Promise<TemplateReviewEventList> {
  return apiGet<TemplateReviewEventList>(
    `/query-templates/${id}/review-events`, undefined, { cache: "no-store" },
  );
}

/** TEMPLATE_AUTHOR */
export function createReviewTemplate(body: TemplateCreateRequest): Promise<ReviewTemplateDetail> {
  return apiPost<TemplateCreateRequest, ReviewTemplateDetail>("/query-templates", body);
}

/** TEMPLATE_AUTHOR — current DRAFT only. */
export function updateReviewTemplate(
  id: number, body: TemplateUpdateRequest,
): Promise<ReviewTemplateDetail> {
  return apiPatch<TemplateUpdateRequest, ReviewTemplateDetail>(`/query-templates/${id}`, body);
}

/** TEMPLATE_AUTHOR */
export function submitReviewTemplate(id: number, note?: string): Promise<ReviewTemplateDetail> {
  return apiPost<{ note?: string }, ReviewTemplateDetail>(
    `/query-templates/${id}/submit-review`, note ? { note } : {},
  );
}

/** TEMPLATE_AUTHOR — from APPROVED/REJECTED current version. */
export function createReviewTemplateVersion(
  id: number, body?: TemplateNewVersionRequest,
): Promise<ReviewTemplateDetail> {
  return apiPost<TemplateNewVersionRequest | Record<string, never>, ReviewTemplateDetail>(
    `/query-templates/${id}/versions`, body ?? {},
  );
}

/** TEMPLATE_APPROVE — server re-checks SQL Safety + Catalog compatibility. */
export function approveReviewTemplate(id: number, note?: string): Promise<ReviewTemplateDetail> {
  return apiPost<{ note?: string }, ReviewTemplateDetail>(
    `/query-templates/${id}/approve`, note ? { note } : {},
  );
}

/** TEMPLATE_APPROVE — reject note is required by the API. */
export function rejectReviewTemplate(id: number, note: string): Promise<ReviewTemplateDetail> {
  return apiPost<{ note: string }, ReviewTemplateDetail>(
    `/query-templates/${id}/reject`, { note },
  );
}

/** TEMPLATE_APPROVE — server re-checks SQL Safety + Catalog compatibility. */
export function enableReviewTemplate(id: number): Promise<ReviewTemplateDetail> {
  return apiPost<Record<string, never>, ReviewTemplateDetail>(
    `/query-templates/${id}/enable`, {},
  );
}

/** TEMPLATE_APPROVE */
export function disableReviewTemplate(id: number): Promise<ReviewTemplateDetail> {
  return apiPost<Record<string, never>, ReviewTemplateDetail>(
    `/query-templates/${id}/disable`, {},
  );
}
