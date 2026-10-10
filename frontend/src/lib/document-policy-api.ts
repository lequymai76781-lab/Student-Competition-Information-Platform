import { apiFetch } from "@/lib/v09-api";

export const documentTypeLabels: Record<string, string> = {
  registration_notice: "报名通知", organization_notice: "组织通知",
  selection_notice: "校赛/选拔通知", recommendation_notice: "推荐通知",
  result_notice: "结果通知", publicity_notice: "公示",
  completion_news: "完赛新闻", competition_intro: "赛事介绍", event_news: "活动新闻",
  policy_recognition_document: "竞赛认定政策", award_policy_document: "竞赛奖励政策",
  postgraduate_policy_document: "推免政策", comprehensive_evaluation_policy_document: "综合测评政策",
  innovation_credit_policy_document: "创新学分政策", repost: "转载/转发",
  deadline_extension: "延期通知", correction_notice: "更正通知",
  rule_update: "规则更新", historical_material: "历史资料", other: "其他",
  policy_recognition: "竞赛认定", award_recognition: "竞赛奖励",
  postgraduate_recommendation_recognition: "推免认可", comprehensive_evaluation_recognition: "综合测评认可",
  innovation_credit_recognition: "创新学分认可",
};

export const primaryDocumentTypeLabels = {
  participation: "参赛相关", result: "结果/公示", information: "赛事信息",
  policy: "政策/认定", update: "更新/更正", repost: "转发", other: "其他",
} as const;
export type PrimaryDocumentType = keyof typeof primaryDocumentTypeLabels;
export const primaryDocumentTypes = Object.entries(primaryDocumentTypeLabels).map(([value, label]) => ({ value, label }));

const legacyPrimaryTypes: Record<string, PrimaryDocumentType> = {
  registration_notice: "participation", organization_notice: "participation",
  selection_notice: "participation", recommendation_notice: "participation",
  result_notice: "result", publicity_notice: "result",
  completion_news: "information", competition_intro: "information", event_news: "information", historical_material: "information",
  policy_recognition_document: "policy", award_policy_document: "policy", postgraduate_policy_document: "policy",
  comprehensive_evaluation_policy_document: "policy", innovation_credit_policy_document: "policy",
  deadline_extension: "update", correction_notice: "update", rule_update: "update",
};

export function primaryDocumentType(value?: string | null): PrimaryDocumentType {
  if (value && Object.hasOwn(primaryDocumentTypeLabels, value)) return value as PrimaryDocumentType;
  return legacyPrimaryTypes[value ?? ""] ?? "other";
}

export const secondaryDocumentTypeLabels: Record<string, string> = {
  ...documentTypeLabels,
  registration: "报名", organization: "组织参赛", selection: "校内选拔", recommendation: "参赛推荐",
  award: "获奖", result: "比赛结果", publicity: "名单公示", recommendation_result: "推荐结果",
  intro: "赛事介绍", completion: "完赛报道", news: "赛事新闻", history: "历史回顾",
  recognition: "竞赛认定", postgraduate: "推免", comprehensive_evaluation: "综合测评",
  innovation_credit: "创新学分", correction: "内容更正", repost: "转发",
};

const operationalLabels: Record<string, string> = {
  pending: "待审核", approved: "已通过", rejected: "已驳回", needs_revision: "待补充", merged: "已合并",
  AUTO_CLASSIFIED: "系统自动识别", HUMAN_CONFIRMED: "人工确认", HUMAN_CORRECTED: "人工修正",
  AUTO_MATCHED: "自动匹配", NEEDS_CONFIRMATION: "待人工确认", NEEDS_QUICK_CONFIRM: "待快速确认",
  NEEDS_MANUAL_MATCH: "待人工匹配", AUTO_RECOGNIZED: "已自动建立关系", HUMAN_RECOGNIZED: "已人工建立关系",
  NEEDS_HUMAN_REVIEW: "待人工审核", BLOCKED: "自动处理受阻", SAFE_AUTO: "可自动处理", QUICK_CONFIRM: "待快速确认", MANUAL: "待人工审核",
  AUTO_POLICY_MATCH: "系统政策匹配", HUMAN_POLICY_MATCH: "人工政策匹配", DOCUMENT_CLASSIFICATION: "文档分类证据",
  human_confirmed: "已人工确认赛事匹配", exact_name: "赛事全称匹配", exact_alias: "赛事别名匹配",
  POLICY: "识别为政策", NON_POLICY: "未识别为政策", NEEDS_POLICY_CONFIRM: "待人工确认",
};

export function documentStatusLabel(value?: string | null): string {
  return operationalLabels[value ?? ""] ?? "待核对";
}

export function documentExplanation(value?: string | null): string {
  if (!value) return "未提供";
  if (operationalLabels[value]) return operationalLabels[value];
  const explanation = value.replace(/^[A-Za-z][A-Za-z0-9_]*\s*[:：]\s*/, "");
  return /[\u3400-\u9fff]/.test(explanation) ? explanation : "需核对原文依据";
}

export type PolicyAssessment = {
  is_policy: boolean;
  policy_confidence?: number | null;
  policy_reason?: string | null;
  policy_status?: string;
  positive_evidence?: string[];
  negative_evidence?: string[];
};

export type DocumentClassificationData = {
  document_type: string;
  primary_type?: string;
  secondary_type?: string | null;
  secondary_types?: string[];
  referenced_primary_type?: string | null;
  policy_assessment?: PolicyAssessment | null;
  is_policy?: boolean;
  policy_confidence?: number | null;
  policy_reason?: string | null;
  policy_status?: string;
  hierarchy_version?: string;
  routing_reason?: string | null;
  confidence?: number | null;
  classification_reason?: string | null;
  matched_rules?: string[];
  requires_human_confirmation?: boolean;
  informational_only?: boolean;
  risk_level?: string;
  classification_status?: string;
  rule_version?: string;
};
export type DocumentTypeOption = { value: string; label: string };
export type ClassificationItem = {
  id: number; title: string; source_url?: string | null;
  school_name?: string | null; competition_name?: string | null;
  status: string; classification?: DocumentClassificationData | null;
  relation_evidence?: { relation_type: string; status: string; source_url?: string | null } | null;
};
export type ClassificationList = {
  items: ClassificationItem[]; total: number;
  statistics?: Record<string, number>;
  document_types?: Array<DocumentTypeOption | string>;
};
export type PolicyAnalysisEntry = {
  raw_competition_name: string; normalized_name?: string | null;
  recognition_type?: string | null; match_status?: string | null;
  match_confidence?: number | null; matched_competition_id?: number | null;
  match_reason?: string | null; verification_method?: string | null;
  candidate_ids?: number[];
  relation_status?: string | null; blocking_reasons?: string[];
  source_title?: string | null; source_url?: string | null;
  effective_from?: string | null; effective_to?: string | null;
  evidence_text?: string | null; locator?: string | null;
};
export type PolicyAnalysis = {
  entries: PolicyAnalysisEntry[]; automatic_relations: number;
  human_confirmed_relations?: number; recognized_relations?: number;
  requires_human_confirmation: boolean; blocking_reasons: string[];
  conflicts: unknown[];
};
export type PolicyItem = {
  id: number; title: string; source_url?: string | null;
  university_id?: number | null; school_name?: string | null;
  classification?: DocumentClassificationData | null;
  analysis?: PolicyAnalysis | null;
};
export type PolicyList = { items: PolicyItem[]; total: number };

const base = "/admin/document-policy";
export const getDocumentClassifications = (offset = 0, limit = 50) => apiFetch<ClassificationList>(`${base}?${new URLSearchParams({ limit: String(limit), offset: String(offset) })}`);
export const correctDocumentClassification = (id: number, document_type: string, reason: string) =>
  apiFetch<ClassificationItem>(`${base}/${id}/classification`, { method: "PUT", body: JSON.stringify({ document_type, reason }) });
export const replayDocumentClassifications = () =>
  apiFetch<unknown>(`${base}/replay-classification`, { method: "POST", body: JSON.stringify({}) });
export const getPolicyAnalyses = (offset = 0, limit = 50) => apiFetch<PolicyList>(`${base}/policies?${new URLSearchParams({ limit: String(limit), offset: String(offset) })}`);
export const analyzePolicy = (id: number) =>
  apiFetch<PolicyAnalysis>(`${base}/policies/${id}/analyze`, { method: "POST", body: JSON.stringify({}) });
export const confirmPolicyMatch = (id: number, raw_competition_name: string, competition_id: number, reason: string) =>
  apiFetch<PolicyAnalysis>(`${base}/policies/${id}/matches`, { method: "PUT", body: JSON.stringify({ raw_competition_name, competition_id, reason }) });
