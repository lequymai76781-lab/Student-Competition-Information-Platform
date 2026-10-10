import type { FieldReview } from "@/lib/field-review-api";

// These are historical machine metadata, not source text or review safety facts.
const machineKeys = new Set(["notice_type", "document_type", "primary_type", "secondary_type", "secondary_types", "referenced_primary_type", "classification", "document_classification", "classification_reason", "classification_status", "matched_rules", "confidence", "policy_assessment", "is_policy", "policy_status", "policy_confidence", "policy_reason", "risk_level", "is_formal_recognition", "source_quality", "suggested_action"]);
const wrapper = /^学校材料\s*·\s*[^·]+\s*·\s*(?:registration_notice|organization_notice|selection_notice|recommendation_notice|policy_recognition|award_policy|repost|competition_notice|other)\s*·\s*/;
export function reviewDisplayTitle(row: FieldReview, blind: boolean): string {
  if (!blind) return row.title;
  return row.source?.source_title?.trim() || row.collection_context?.source_title?.trim() || row.relation?.source?.source_title?.trim() || row.fields.flatMap(field => field.proposals).find(proposal => proposal.source?.source_title?.trim())?.source?.source_title?.trim() || row.title.replace(wrapper, "");
}
export function reviewDisplayFlags(flags: string[] | undefined, blind: boolean): string[] {
  return (flags ?? []).filter(flag => !blind || !/^(?:DOCUMENT_|CLASSIFICATION_|SHADOW_|LOW_RISK(?:\b|$)|HIGH_RISK(?:\b|$))/.test(flag));
}
export function reviewDisplayNotes(value: string | null | undefined, blind: boolean): string {
  if (!value || !blind) return value ?? "";
  return value.replace(/原资料细分类为[^。\n]*(?:。|$)/g, "").replace(/导入通知类型映射为[^。\n]*(?:。|$)/g, "").trim();
}
function withoutMachineMetadata(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withoutMachineMetadata);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(Object.entries(value).flatMap(([key, item]) => {
    if (machineKeys.has(key) || key.startsWith("shadow_") || key.startsWith("classification_")) return [];
    if ((key === "flags" || key === "risk_reasons") && Array.isArray(item)) return [[key, reviewDisplayFlags(item.filter((flag): flag is string => typeof flag === "string"), true)]];
    if (key === "evidence_notes" && typeof item === "string") return [[key, reviewDisplayNotes(item, true)]];
    if ((key === "title" || key === "source_title") && typeof item === "string") return [[key, item.replace(wrapper, "")]];
    return [[key, withoutMachineMetadata(item)]];
  }));
}
export function reviewDisplayRecord(value: unknown, blind: boolean): string {
  if (value == null) return "";
  if (typeof value !== "string") return JSON.stringify(blind ? withoutMachineMetadata(value) : value, null, 2) ?? "";
  if (!blind) return value;
  // Collector descriptions have an identity marker followed by one JSON envelope.
  const start = value.indexOf("{");
  if (start >= 0) {
    try { return value.slice(0, start) + JSON.stringify(withoutMachineMetadata(JSON.parse(value.slice(start))), null, 2); }
    catch { /* A source paragraph may contain braces: keep its text intact. */ }
  }
  return reviewDisplayNotes(value, true).split("\n").filter(line => !/^\s*(?:notice_type|document_type|primary_type|secondary_type|risk_level|机器分类|系统分类|材料类型)\s*[:：]/i.test(line)).join("\n");
}
