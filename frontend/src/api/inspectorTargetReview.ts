import { apiGet } from "./client";
import type { InspectorTargetReview } from "../types/inspectorTargetReview";

/** GET is configuration-only; never calls /inspect, /capture or /test-connection. */
export function reviewInspectorTarget(profileId: number): Promise<InspectorTargetReview> {
  return apiGet<InspectorTargetReview>(
    `/connection-profiles/${profileId}/inspector-target-review`,
  );
}
