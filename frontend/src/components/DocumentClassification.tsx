"use client";

import { useState } from "react";
import { correctDocumentClassification, documentExplanation, documentStatusLabel, primaryDocumentType, primaryDocumentTypeLabels, primaryDocumentTypes, secondaryDocumentTypeLabels, type DocumentClassificationData, type DocumentTypeOption } from "@/lib/document-policy-api";

export function DocumentClassification({ classification, candidateId, onUpdated }: {
  classification: DocumentClassificationData;
  candidateId?: number;
  documentTypes?: Array<DocumentTypeOption | string>;
  onUpdated?: (classification: DocumentClassificationData) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<string>(primaryDocumentType(classification.primary_type || classification.document_type));
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const primary = primaryDocumentType(classification.primary_type || classification.document_type);
  const semanticTypes = [classification.secondary_type || classification.document_type, ...(classification.secondary_types ?? [])];
  const semanticLabels = [...new Set(semanticTypes.map((value) => value === "award" && primary === "policy" ? "竞赛奖励" : secondaryDocumentTypeLabels[value]).filter(Boolean))];
  const policy = classification.policy_assessment ?? (classification.is_policy != null ? {
    is_policy: classification.is_policy, policy_confidence: classification.policy_confidence,
    policy_reason: classification.policy_reason, policy_status: classification.policy_status,
  } : null);
  const policyNeedsReview = policy?.policy_status === "NEEDS_POLICY_CONFIRM";
  const showPolicy = primary === "policy" || policy?.is_policy || policyNeedsReview;
  const highRisk = primary === "update" || classification.risk_level === "HIGH_RISK";
  async function save() {
    if (!candidateId || !selected || !reason.trim() || busy) return;
    setBusy(true); setError("");
    try {
      const updated = await correctDocumentClassification(candidateId, selected, reason.trim());
      if (updated.classification) onUpdated?.(updated.classification);
      setEditing(false); setReason("");
    } catch (exc) { setError(exc instanceof Error ? exc.message : "分类修正失败，请重试。"); }
    finally { setBusy(false); }
  }
  return <section aria-label="系统文档分类" className="rounded-lg border border-line p-3 text-sm">
    <p><strong>系统分类：</strong>{primaryDocumentTypeLabels[primary]}</p>
    {semanticLabels.length ? <p className="mt-1">二级标签（可选）：{semanticLabels.join("、")}</p> : null}
    {primary === "repost" && classification.referenced_primary_type ? <p className="mt-1">转发内容类型：{primaryDocumentTypeLabels[primaryDocumentType(classification.referenced_primary_type)]}</p> : null}
    <p className="mt-1">规则置信分：{classification.confidence == null ? "未提供" : `${Math.round(classification.confidence * 100)}%`}（规则评分，未经人工校准）</p>
    {classification.classification_reason ? <p className="mt-1 whitespace-pre-wrap">分类依据：{documentExplanation(classification.classification_reason)}</p> : null}
    <p className="mt-1 text-xs text-muted">{classification.classification_status === "AUTO_CLASSIFIED" ? "系统自动识别，无需再次选择类型。" : classification.requires_human_confirmation ? "分类需要人工确认，可通过修改分类处理。" : "分类结果已保存。"} 二级标签仅描述语义，不要求再次确认。</p>
    <p className="mt-1 text-xs text-muted">分类不代表事实获批；字段和关系仍须单独审核。{classification.informational_only ? " 此材料仅供参考。" : ""}</p>
    {highRisk ? <p className="mt-2 rounded-md bg-amber-50 p-2 text-amber-900">高风险：材料涉及更新、更正或重要事实变化，必须进入字段审核；分类确认不会批准事实修改。</p> : null}
    {primary === "repost" ? <p className="mt-2 text-amber-900">转发材料不能作为原始官方依据；正式事实与政策认可需核对原始来源。</p> : null}
    {showPolicy ? <div className="mt-2 rounded-md bg-amber-50 p-2 text-amber-900">
      <p>政策判定：{policy ? documentStatusLabel(policy.policy_status || (policy.is_policy ? "POLICY" : "NON_POLICY")) : "待人工确认"}{policy?.policy_confidence != null ? `（规则评分 ${Math.round(policy.policy_confidence * 100)}%）` : ""}</p>
      {policy?.policy_reason ? <p className="mt-1">判定依据：{documentExplanation(policy.policy_reason)}</p> : null}
      <p className="mt-1">政策文档分类不代表正式认可；赛事抽取、名称匹配和关系认定分别核验，来源、有效期与版本冲突仍需检查。</p>
    </div> : null}
    {candidateId && !editing ? <button type="button" className="button-secondary mt-3 text-xs" onClick={() => { setSelected(primary); setError(""); setEditing(true); }}>修改分类</button> : null}
    {editing ? <div className="mt-3 space-y-3">
      <label className="grid gap-1">修正后的文档类型<select className="field" disabled={busy} value={selected} onChange={(event) => setSelected(event.target.value)}>{primaryDocumentTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
      <label className="grid gap-1">分类修正依据<textarea className="field min-h-20 py-2" disabled={busy} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
      <div className="flex gap-2"><button type="button" className="button-primary" disabled={busy || !reason.trim()} onClick={() => void save()}>保存分类修正</button><button type="button" className="button-secondary" disabled={busy} onClick={() => { setEditing(false); setError(""); }}>取消</button></div>
    </div> : null}
    {error ? <p role="alert" className="mt-2 text-red-700">{error}</p> : null}
  </section>;
}
