import { apiFetch } from "@/lib/v09-api";
import type { DocumentClassificationData } from "@/lib/document-policy-api";

export type ReviewEntity = "competition" | "edition";
export type ReviewValue = string | number | boolean | null | ReviewValue[] | { [key: string]: ReviewValue };
export type ReviewSource = {
  source_type: string | null;
  source_title?: string | null;
  source_url?: string | null;
  publisher?: string | null;
  published_at?: string | null;
  collected_at?: string | null;
  verified_at?: string | null;
  verified_by?: number | null;
  verification_state?: string;
  availability?: { status: string; checked_at?: string | null; status_code?: number | null };
  access_status?: string | null; source_failure_reason?: string | null; source_failure_detail?: string | null;
  accessed_at?: string | null; fetched_at?: string | null; evidence_notes?: string | null;
};
export type ReviewProposal = { id: string; candidate_value: ReviewValue; source?: ReviewSource | null; confidence?: number | null };
export type ReviewField = {
  field_name: string; display_name: string; current_value: ReviewValue; candidate_value: ReviewValue;
  changed: boolean; change_type: "add" | "modify" | "delete" | "unchanged";
  verification_state: string; source?: ReviewSource | null; source_url?: string | null;
  source_type?: string | null; confidence?: number | null; last_verified_at?: string | null;
  decision: "pending" | "approved" | "rejected" | "deferred";
  proposals: ReviewProposal[];
  timeline?: ReviewTimelineEntry[]; timeline_total?: number; risk_reasons?: string[];
  conflicts?: Array<{ candidate_id: number; proposal_id: string; candidate_value: ReviewValue; source?: ReviewSource | null }>;
};
export type ReviewTimelineEntry = { candidate_id: number; proposal_id: string; candidate_value: ReviewValue; source?: ReviewSource | null; scope?: string | Record<string, unknown>; announcement_hint?: string | boolean | null };
export type ReviewDecision = { field_name: string; action: "approve" | "reject" | "defer"; proposal_id?: string; confirm_delete?: boolean };
export type ReviewHistory = {
  action?: string; reviewer_id?: number | null; reviewed_at?: string | null; note?: string | null;
  decisions?: Array<{ field_name?: string; action: string }>; before?: unknown; after?: unknown; sources?: unknown;
};
export type FieldReview = {
  id: number; title: string; description?: string | null; entity_type: ReviewEntity;
  competition_id?: number | null; competition_name?: string | null; edition_id?: number | null;
  year?: number | null; university_id?: number | null; submitter_id?: number | null;
  origin: string; status: string; created_at: string; preview_token: string;
  origin_source_url?: string | null; source?: ReviewSource | null;
  document_classification?: DocumentClassificationData | null;
  collection_context?: {
    kind: string; source_quality: string; source_failure_reason?: string | null;
    source_type?: string; source_title?: string; publisher?: string;
    accessed_at?: string; published_at?: string | null; evidence_notes?: string | null;
    school_name?: string; school_source_name?: string; notice_type?: string;
    is_formal_recognition?: boolean; recognition_evidence?: string | null;
    school_deadline?: string | null; year?: number | null; edition_id?: number | null;
    edition_status?: string;
  } | null;
  relation?: SchoolRelationReview | null;
  risk_level?: "LOW_RISK" | "HIGH_RISK" | "NORMAL"; risk_reasons?: string[]; low_risk_fields?: string[];
  fields: ReviewField[]; flags: string[]; history: ReviewHistory[]; bulk_eligible_fields: string[];
};
export type FieldReviewConfig = {
  fields: Record<ReviewEntity, Array<{ field_name: string; display_name: string; value_type: string }>>;
  source_types: Array<{ value: string; label: string; priority: number }>;
};
export type FieldReviewInput = {
  entity_type: ReviewEntity; competition_id?: number; edition_id?: number; year?: number;
  title: string; description?: string; university_id?: number; origin?: string;
  fields: Array<{ field_name: string; candidate_value: ReviewValue; source?: ReviewSource; confidence?: number }>;
};
export type FieldReviewFilters = {
  status?: string; flag?: string; entity_type?: string; competition_id?: string;
  university_id?: string; source_type?: string; submitter_id?: string;
  created_from?: string; created_to?: string;
  risk?: string; search?: string; relation_type?: string; sort?: string;
};

const base = "/admin/field-reviews";
export const fieldReviewConfig = () => apiFetch<FieldReviewConfig>(`${base}/config`);
export function fieldReviews(filters: FieldReviewFilters, limit: number, offset: number) {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  for (const [key, value] of Object.entries(filters)) if (value) query.set(key, value);
  return apiFetch<{ items: FieldReview[]; total: number }>(`${base}?${query}`);
}
export const fieldReviewSources = (id: number, field_name: string, offset: number) => apiFetch<{ items: ReviewTimelineEntry[]; total: number }>(`${base}/${id}/sources?${new URLSearchParams({ field_name, limit: "20", offset: String(offset) })}`);
export const fieldReview = (id: number) => apiFetch<FieldReview>(`${base}/${id}`);
export const createFieldReview = (payload: FieldReviewInput) => apiFetch<FieldReview>(base, { method: "POST", body: JSON.stringify(payload) });
export const prepareFieldReview = (id: number, payload: FieldReviewInput & { preview_token: string }) => apiFetch<FieldReview>(`${base}/${id}/prepare`, { method: "PUT", body: JSON.stringify(payload) });
export const verifyFieldReviewSource = (id: number, proposalId: string, preview_token: string, note: string) => apiFetch<FieldReview>(`${base}/${id}/sources/${encodeURIComponent(proposalId)}/verify`, { method: "POST", body: JSON.stringify({ preview_token, note }) });
export const decideFieldReview = (id: number, preview_token: string, note: string, decisions: ReviewDecision[], learningSessionId?: string) => apiFetch<FieldReview>(`${base}/${id}/review`, { method: "POST", ...(learningSessionId ? { headers: { "X-Review-Learning-Session": learningSessionId } } : {}), body: JSON.stringify({ preview_token, note, decisions }) });
export const rejectUnstructuredFieldReview = (id: number, preview_token: string, note: string, learningSessionId?: string) => apiFetch<FieldReview>(`${base}/${id}/reject-unstructured`, { method: "POST", ...(learningSessionId ? { headers: { "X-Review-Learning-Session": learningSessionId } } : {}), body: JSON.stringify({ preview_token, note }) });
export const bulkApproveFieldReview = (row: FieldReview, field_names: string[], note: string) => apiFetch<unknown>(`${base}/bulk-review`, { method: "POST", body: JSON.stringify({ items: [{ id: row.id, preview_token: row.preview_token, field_names }], note }) });
export const stageFieldReviewOrigin = (kind: "correction" | "supplement", id: number) => apiFetch<{ field_review_id: number }>(`/admin/field-review-origins/${kind}/${id}`, { method: "POST" });

export type ReviewBatchItem = { id: number; preview_token: string; field_names: string[] };
export type ReviewBatchPayload = { items: ReviewBatchItem[]; note: string };
export type ReviewBatchPreview = { items: FieldReview[]; total: number; field_count: number; transaction: "atomic" };
export type ReviewBatchResult = { items: FieldReview[]; total: number; succeeded: number; failed: number; pending_ids: number[]; transaction: "atomic" };
export const previewFieldReviewBatch = (payload: ReviewBatchPayload) => apiFetch<ReviewBatchPreview>(base + "/bulk-preview", { method: "POST", body: JSON.stringify(payload) });
export const approveFieldReviewBatch = (payload: ReviewBatchPayload) => apiFetch<ReviewBatchResult>(base + "/bulk-review", { method: "POST", body: JSON.stringify(payload) });

export type ReviewMode = "human" | "automation";
export type ReviewTimingEvent = "source_open" | "decision" | "submit";
export type ReviewTimingSession = { session_id: string; candidate_id: number; candidate_ids?: number[]; sample_type?: "single" | "batch"; reviewer_id?: number; mode: ReviewMode; status: string; started_at?: string; last_event_at?: string; completed_at?: string | null; elapsed_seconds?: number | null; phase_seconds?: { source_open?: number | null; decision?: number | null; submit?: number | null } };
export type ReviewTimingSummary = { completed_samples: number; completed_candidates?: number; active_sessions: number; interrupted_sessions: number; mean_seconds: number | null; median_seconds: number | null; p90_seconds: number | null; theoretical_per_hour: number | null; by_sample_type?: Record<"single" | "batch", ReviewTimingSummary> };
export type ReviewStatistics = { counts: Record<string, number>; telemetry: { groups: Record<ReviewMode, ReviewTimingSummary>; processed_candidates?: number; unknown_duration_candidates?: number } };
export const fieldReviewStatistics = () => apiFetch<ReviewStatistics>(base + "/statistics");
export const startReviewTiming = (id: number, mode: ReviewMode, candidate_ids?: number[]) => apiFetch<ReviewTimingSession>(base + "/" + id + "/timing/start", { method: "POST", body: JSON.stringify({ mode, ...(candidate_ids ? { candidate_ids } : {}) }) });
export const sendReviewTimingEvent = (id: number, payload: { session_id: string; event: ReviewTimingEvent; proposal_id?: string; field_name?: string; decision?: "approve" | "reject" | "defer" }) => apiFetch<ReviewTimingSession>(base + "/" + id + "/timing/event", { method: "POST", body: JSON.stringify(payload) });
export type SchoolRelationPrepared = {
  scope_type?: "university" | "college" | "major" | null; college_id?: number | null; major_id?: number | null;
  student_scope?: "undergraduate" | "graduate" | "all" | "other" | null; applicability_text?: string | null;
  effective_from?: string | null; effective_until?: string | null; validity_note?: string | null;
  current_validity_confirmed?: boolean; recognition_evidence?: string | null; revoked?: boolean;
};
export type SchoolRelationReview = {
  candidate_id: number; status: string; preview_token: string; relation_kind: "notice" | "policy";
  university_id?: number | null; school_name?: string | null; competition_id?: number | null; competition_name?: string | null;
  notice_type: string; year?: number | null; edition_id?: number | null; source?: ReviewSource | null;
  prepared: SchoolRelationPrepared; flags: string[]; blocking_reasons: string[]; can_approve: boolean;
  existing_records: Array<{ id: number; record_type: "notice" | "policy"; [key: string]: unknown }>;
  decision?: { action: "approve" | "reject" | "defer"; reviewer_id?: number; reviewed_at?: string; note?: string; record_id?: number; record_type?: string } | null;
  history: ReviewHistory[];
};
export type SchoolRelationPrepare = SchoolRelationPrepared & { preview_token: string; note: string; university_id?: number; competition_id?: number; identity_evidence?: string; year?: number; edition_id?: number };
export const prepareSchoolRelation = (id: number, payload: SchoolRelationPrepare) => apiFetch<SchoolRelationReview>(base + "/" + id + "/relation/prepare", { method: "PUT", body: JSON.stringify(payload) });
export const verifySchoolRelation = (id: number, preview_token: string, note: string) => apiFetch<SchoolRelationReview>(base + "/" + id + "/relation/verify-source", { method: "POST", body: JSON.stringify({ preview_token, note }) });
export const decideSchoolRelation = (id: number, preview_token: string, note: string, action: "approve" | "reject" | "defer", learningSessionId?: string) => apiFetch<SchoolRelationReview>(base + "/" + id + "/relation/review", { method: "POST", ...(learningSessionId ? { headers: { "X-Review-Learning-Session": learningSessionId } } : {}), body: JSON.stringify({ preview_token, note, action }) });
