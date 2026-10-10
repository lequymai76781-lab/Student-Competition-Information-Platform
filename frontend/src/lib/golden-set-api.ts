import { apiFetch } from "@/lib/v09-api";

export type AnnotationStatus = "annotated" | "draft" | "skipped";
export type AuditKind = "policies" | "relations";
export type Answer = "yes" | "no" | "unsure";
export type GoldenProgress = { annotated: number; draft: number; skipped: number; untouched: number; total: number };
export type GoldenAnnotation = {
  status: AnnotationStatus; human_primary_type: string | null; human_secondary_types: string[]; note: string;
  annotated_by: string | number; annotated_at: string; skipped: boolean; revision: number;
  prediction_exposed: boolean; predicted_type: string; predicted_confidence: number | null;
  source_id: string | number; title: string; informational_safe?: Answer | null;
};
export type GoldenSource = {
  source_id: string | number; title: string; school_name: string | null; publisher: string | null;
  published_at: string | null; source_url: string | null; content_preview: string | null; body_available: boolean;
  predicted_type: string; predicted_confidence: number | null; predicted_secondary_types: string[];
  matched_rules: string[]; classification_reason: string | null; prediction_exposed: boolean; annotation: GoldenAnnotation | null;
};
export type GoldenSet = {
  dataset_id: string; total: number; items: GoldenSource[]; progress: GoldenProgress;
  document_types: Array<{ value: string; label: string } | string>; audit_sets: unknown;
};
export type AnnotationInput = {
  status: AnnotationStatus; human_primary_type: string | null; human_secondary_types: string[]; note: string;
  expected_revision: number; prediction_exposed: boolean; informational_safe?: Answer | null;
};
export type AuditAnnotation = {
  status: AnnotationStatus; answers: Record<string, Answer>; note: string; revision: number;
  annotated_by: string | number; annotated_at: string;
};
export type AuditItem = {
  audit_id: string | number; title: string; school_name: string | null; source_url: string | null;
  content_preview: string | null; entries: Array<Record<string, unknown>>;
  publisher?: string | null; published_at?: string | null; effective_from?: string | null; effective_until?: string | null;
  policy_url?: string | null; attachment_url?: string | null; blocking_reasons?: string[];
  competition_name: string | null; raw_competition_name: string | null; recognition_type: string | null;
  annotation: AuditAnnotation | null;
};
export type AuditSet = { items: AuditItem[]; progress: GoldenProgress; checks: Array<{ key: string; label: string }> };
export type AuditInput = { status: AnnotationStatus; answers: Record<string, Answer>; note: string; expected_revision: number };
export type GoldenMetrics = Record<string, unknown>;
const base = "/admin/golden-set";
export const getGoldenSet = () => apiFetch<GoldenSet>(base);
export const saveGoldenAnnotation = (id: string | number, input: AnnotationInput) =>
  apiFetch<{ annotation: GoldenAnnotation; progress: GoldenProgress }>(`${base}/annotations/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(input) });
export const exposeGoldenPrediction = (id: string | number) =>
  apiFetch<{ prediction_exposed: boolean }>(`${base}/exposure/${encodeURIComponent(id)}`, { method: "POST", body: "{}" });
export const getGoldenAudits = (kind: AuditKind) => apiFetch<AuditSet>(`${base}/audits/${kind}`);
export const saveGoldenAudit = (kind: AuditKind, id: string | number, input: AuditInput) =>
  apiFetch<{ annotation: AuditAnnotation; progress: GoldenProgress }>(`${base}/audits/${kind}/${encodeURIComponent(id)}`, { method: "PUT", body: JSON.stringify(input) });
export const getGoldenMetrics = () => apiFetch<GoldenMetrics>(`${base}/metrics`);
export const exportGoldenSet = () => apiFetch<Record<string, unknown>>(`${base}/export`);

