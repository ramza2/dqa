import { apiGet, apiPost } from "./client";
import type {
  ReviewTemplateDetail, ReviewTemplateList, TemplateSqlSafetyReview,
} from "../types/templateReview";

/** TEMPLATE_READ is enforced by the existing backend; no new authority. */
export function listReviewTemplates(sourceName: string, offset = 0): Promise<ReviewTemplateList> {
  return apiGet<ReviewTemplateList>("/query-templates", {
    source_name: sourceName.trim() || undefined, limit: 50, offset,
  }, { cache: "no-store" });
}
export function getReviewTemplate(id: number): Promise<ReviewTemplateDetail> {
  return apiGet<ReviewTemplateDetail>(`/query-templates/${id}`, undefined, { cache: "no-store" });
}
export function getReviewTemplateSqlSafety(id: number): Promise<TemplateSqlSafetyReview> {
  return apiGet<TemplateSqlSafetyReview>(`/query-templates/${id}/sql-safety`, undefined, { cache: "no-store" });
}

export interface TemplateReviewActor {
  actor_id: string;
  roles: string[];
  provider: string;
}
export type ReviewAction = "submit-review" | "approve" | "reject";
export type ReviewActionBody = {
  note: string;
  expected_version_id: number;
  expected_updated_at: string;
};

/** Loading the actor is opt-in, to preserve M3-C1's read-only-by-default UI. */
export function getTemplateReviewActor(): Promise<TemplateReviewActor> {
  return apiGet<TemplateReviewActor>("/auth/me", undefined, { cache: "no-store" });
}
export function postReviewAction(
  templateId: number,
  action: ReviewAction,
  body: ReviewActionBody,
): Promise<ReviewTemplateDetail> {
  return apiPost<ReviewActionBody, ReviewTemplateDetail>(
    `/query-templates/${templateId}/${action}`,
    body, { cache: "no-store" },
  );
}
