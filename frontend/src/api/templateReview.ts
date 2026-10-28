import { apiGet } from "./client";
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
