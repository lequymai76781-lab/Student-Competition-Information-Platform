"use client";

import Link from "next/link";
import { reviewDisplayFlags, reviewDisplayNotes, reviewDisplayRecord, reviewDisplayTitle } from "@/lib/review-learning-display";
import { reviewCandidateComplete, StartReviewTiming, useReviewTiming } from "@/components/ReviewTelemetry";
import { SchoolRelationReview } from "@/components/SchoolRelationReview";
import { ReviewLearningControls, useReviewLearning } from "@/components/ReviewLearning";
import { DocumentClassification } from "@/components/DocumentClassification";
import { useState, type MouseEvent } from "react";
import { fieldReviewSources, bulkApproveFieldReview, decideFieldReview, rejectUnstructuredFieldReview, verifyFieldReviewSource, type FieldReview, type FieldReviewConfig, type ReviewDecision, type ReviewField, type ReviewSource, type ReviewValue, type ReviewTimelineEntry } from "@/lib/field-review-api";

export const fieldReviewStatusLabels: Record<string, string> = { pending: "待审核", approved: "已批准", rejected: "已拒绝", partially_approved: "部分批准", deferred: "暂缓处理" };
export const fieldReviewFlagLabels: Record<string, string> = { CONFLICT: "来源冲突", NO_SOURCE: "缺少来源", UNVERIFIED: "来源未核验", DUPLICATE_SUSPECTED: "身份或重复待确认", edition_uncertain: "届次待确认", LOW_RISK: "低风险", HIGH_RISK: "高风险", RELATION_CONFLICT: "学校关系冲突", IMPORTANT_FIELD: "重要身份或时间字段", OVERWRITE_EXISTING: "覆盖已有正式值", DELETE_VALUE: "删除正式值", WEAK_SOURCE: "来源强度不足", ENTITY_UNCERTAIN: "实体身份待确认", SCHOOL_RELATION: "学校关系须逐条审核", UNSTRUCTURED: "尚未结构化" };
const noticeLabels: Record<string, string> = { registration_notice: "报名通知", organization_notice: "组织参赛通知", selection_notice: "校内选拔", recommendation_notice: "推荐参赛", policy_recognition: "正式认定政策", award_policy: "奖励政策", repost: "转载信息", competition_notice: "赛事通知", other: "其他材料" };
const changeLabels = { add: "新增", modify: "修改", delete: "删除", unchanged: "未变化" };
const decisionLabels = { pending: "待处理", approved: "已批准", rejected: "已拒绝，保留原值", deferred: "已暂缓" };
export function reviewValue(value: unknown): string { return value == null ? "（空值）" : typeof value === "string" ? value || "（空字符串）" : JSON.stringify(value, null, 2); }
function time(value?: string | null) {
  if (!value) return "未记录";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return `${value}（日期精度）`;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("zh-CN", { timeZone: "Asia/Shanghai", hour12: false });
}
function verified(source?: ReviewSource | null) { return Boolean(source?.verification_state === "VERIFIED" && source?.verified_at && source?.verified_by != null); }
function clearing(value: ReviewValue) { return value === null || value === "" || (Array.isArray(value) && value.length === 0); }
function changeType(current: ReviewValue, candidate: ReviewValue): keyof typeof changeLabels {
  if (JSON.stringify(current) === JSON.stringify(candidate)) return "unchanged";
  if (candidate === null) return "delete";
  return current === null ? "add" : "modify";
}

export function FieldReviewDetail({ row, config, onReload, onPrepare, onMessage, onSelect, onUpdated, onQueueReload }: { row: FieldReview; config: FieldReviewConfig; onReload: () => void; onPrepare: () => void; onMessage: (message: string) => void; onSelect: (id: number) => void; onUpdated?: (row: FieldReview) => void; onQueueReload?: () => void }) {
  const timing = useReviewTiming();
  const learning = useReviewLearning();
  const [choices, setChoices] = useState<Record<string, { action?: ReviewDecision["action"]; proposalId?: string; confirmDelete?: boolean }>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [batch, setBatch] = useState<string[]>([]);
  const completed = reviewCandidateComplete(row);
  const context = row.collection_context;
  const schoolMapping = context?.kind === "school_mapping";
  function choose(field: string, patch: { action?: ReviewDecision["action"]; proposalId?: string; confirmDelete?: boolean }) { setChoices((values) => ({ ...values, [field]: { ...values[field], ...patch } })); if (patch.action) { void timing.record(row.id, "decision", { field_name: field, decision: patch.action }); void learning.record(row.id, "decision", { field_name: field, decision: patch.action }); } }
  const decisions: ReviewDecision[] = row.fields.flatMap((field) => {
    const selected = choices[field.field_name];
    if (!selected?.action || ["approved", "rejected"].includes(field.decision)) return [];
    return [{ field_name: field.field_name, action: selected.action,
      ...(selected.action === "approve" ? { proposal_id: selected.proposalId, ...(selected.confirmDelete ? { confirm_delete: true } : {}) } : {}) }];
  });
  const invalid = decisions.some((decision) => {
    if (decision.action !== "approve") return false;
    const field = row.fields.find((item) => item.field_name === decision.field_name)!;
    const selected = field.proposals.find((item) => item.id === decision.proposal_id);
    return !selected || !verified(selected.source) || (clearing(selected.candidate_value) && !clearing(field.current_value) && !decision.confirm_delete);
  });
  async function act(action: () => Promise<unknown>, message: string, submit = false) {
    if (busy) return;
    setBusy(true); setError("");
    try { if (submit) { await learning.beforeSubmit(row.id); await timing.record(row.id, "submit"); } const result = await action(); if (submit) await learning.complete(row.id); if (result && typeof result === "object") { const results = "items" in result && Array.isArray(result.items) ? result.items as FieldReview[] : "fields" in result ? [result as FieldReview] : []; timing.finish(results.filter(reviewCandidateComplete).map((item) => item.id)); } if (result && typeof result === "object" && "id" in result && "preview_token" in result) onUpdated?.(result as FieldReview); onMessage(message); onReload(); }
    catch (exc) { if (submit) learning.businessFailed(row.id); setError(exc instanceof Error ? exc.message : "审核操作失败，请重试。"); }
    finally { setBusy(false); }
  }
  function trackSourceOpen(event: MouseEvent<HTMLElement>) {
    if (event.type === "auxclick" && event.button !== 1) return;
    const link = (event.target as HTMLElement).closest("a");
    if (link?.target === "_blank" && !link.hasAttribute("data-review-source") && /^https?:/i.test(link.href)) { void timing.record(row.id, "source_open"); void learning.record(row.id, "source_open"); }
  }
  return <article className="min-w-0 space-y-4" aria-label="候选详情" onClickCapture={trackSourceOpen} onAuxClickCapture={trackSourceOpen}>
    <StartReviewTiming candidateId={row.id} />
    <ReviewLearningControls candidateId={row.id} completed={completed} />
    <div className="panel p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="break-words text-xl font-semibold">{reviewDisplayTitle(row, learning.blind)}</h2><p className="mt-2 text-sm text-muted">候选 #{row.id} · {row.entity_type === "edition" ? `届次 ${row.year ?? "年份待补充"} · ID ${row.edition_id ?? "待创建"}` : "赛事本体"} · {fieldReviewStatusLabels[row.status] ?? row.status}</p></div>
        {row.competition_id ? <Link className="button-secondary text-sm" href={`/competitions/${row.competition_id}${row.edition_id ? `?edition_id=${row.edition_id}` : ""}`}>查看正式详情</Link> : null}</div>
      {context ? <section aria-label="采集材料摘要" className="mt-4 space-y-2 rounded-lg border border-line p-4 text-sm">
        {!learning.blind ? <p>来源等级 {context.source_quality} · 仅供审核排序，不代表已核验或批准</p> : null}
        {schoolMapping ? <><p><strong>{context.school_name}</strong>{!learning.blind ? <> · <span>{noticeLabels[context.notice_type ?? ""] ?? context.notice_type}</span></> : null}</p>
          <p>来源部门：{context.school_source_name || context.publisher || "未记录"}</p>
          <p>届次：{context.year ?? "未明确"} · {context.edition_status === "existing" ? `对应届次 ID ${context.edition_id}` : context.edition_status === "year_known_pending_edition" ? "年份明确，正式届次尚未建立" : "需要人工确认，不自动匹配"}</p>
          {!learning.blind ? <p>{context.is_formal_recognition ? "材料包含该赛事的认定依据，尚待人工审核。" : "未提供该赛事的正式认定证据；发布通知不等于正式认定。"}</p> : null}
          {context.recognition_evidence ? <p className="whitespace-pre-wrap">{context.recognition_evidence}</p> : null}
          {context.school_deadline ? <p>校内截止：{context.school_deadline}（不替代全国截止）</p> : null}
        </> : null}
        {context.evidence_notes ? <p className="whitespace-pre-wrap">{reviewDisplayNotes(context.evidence_notes, learning.blind)}</p> : null}
        <p>原文发布时间：{time(context.published_at)} · 资料读取时间：{time(context.accessed_at)}</p>
        {context.source_failure_reason ? <p className="text-amber-800">来源访问失败：{context.source_failure_reason}</p> : null}
        <details><summary className="cursor-pointer text-accent">查看完整采集记录</summary><pre className="mt-2 whitespace-pre-wrap break-words text-xs">{reviewDisplayRecord(row.description, learning.blind)}</pre></details>
      </section> : <p className="mt-3 whitespace-pre-wrap break-words text-sm">{reviewDisplayRecord(row.description, learning.blind) || "未填写原始说明"}</p>}
      {row.origin_source_url && /^https?:\/\//i.test(row.origin_source_url) ? <a className="mt-3 inline-block break-all text-sm text-accent underline" href={row.origin_source_url} target="_blank" rel="noopener noreferrer">查看提交时的原始来源（尚未核验）</a> : null}
      <p className="mt-3 text-xs text-muted">{row.competition_name ?? "新赛事"} · 提交人 {row.submitter_id ?? "未记录"} · 提交于 {time(row.created_at)} · 关联学校 {row.university_id ?? "未指定"}</p>
      <div className="mt-3 flex flex-wrap gap-2">{reviewDisplayFlags(row.flags, learning.blind).map((flag) => <span key={flag} className="badge border-amber-200 bg-amber-50 text-amber-800">{fieldReviewFlagLabels[flag] ?? flag}</span>)}</div>
    </div>
    {!learning.blind && row.document_classification && !(schoolMapping && row.relation) ? <div className="panel p-5"><DocumentClassification classification={row.document_classification} /></div> : null}
    {error ? <div role="alert" className="panel border-red-200 p-4 text-sm text-red-700">{error}<button type="button" className="ml-3 underline" onClick={onReload}>重新加载预览</button></div> : null}
    {schoolMapping && row.relation ? <SchoolRelationReview key={row.id} initial={row.relation} classification={row.document_classification} onQueueReload={onQueueReload ?? onReload} onCompleted={(message) => { onMessage(message); onReload(); }} /> : !row.fields.length ? <div className="panel p-5"><h3 className="font-semibold">{completed ? "原始材料已处理" : "原始补充待整理"}</h3>{!completed ? <><p className="my-3 text-sm text-muted">先确认对应赛事、届次、字段和值，再逐一核对来源；无关或重复材料可以直接拒绝并记录原因。</p>{schoolMapping ? <p className="text-amber-800">学校映射材料保留待审。当前页面支持查看证据或拒绝材料，尚不支持批准为正式学校关系；不能转成赛事本体字段。</p> : <button className="button-primary" type="button" disabled={busy} onClick={onPrepare}>整理为字段候选</button>}<label className="mt-4 grid gap-2 text-sm">拒绝说明<textarea className="field min-h-20 py-2" disabled={busy} value={note} onChange={(event) => setNote(event.target.value)} /></label><button className="button-secondary mt-3" type="button" disabled={busy || !note.trim() || !learning.canSubmit(row.id)} onClick={() => act(() => rejectUnstructuredFieldReview(row.id, row.preview_token, note.trim(), learning.enabled ? learning.entries[row.id]?.session?.session_id : undefined), "原始材料已拒绝，正式数据未改变。", true)}>拒绝此原始材料</button></> : <p className="mt-3 text-sm text-muted">处理结果和理由已保留在审核历史中，未修改正式字段。</p>}</div> : <fieldset disabled={busy || completed} className="min-w-0 space-y-4">
      {row.fields.map((field) => {
        const selection = choices[field.field_name] ?? {};
        const chosen = field.proposals.find((item) => item.id === selection.proposalId);
        const settled = ["approved", "rejected"].includes(field.decision);
        const needsDelete = chosen && clearing(chosen.candidate_value) && !clearing(field.current_value);
        return <section key={field.field_name} className="panel min-w-0 p-4 sm:p-5" aria-label={`${field.display_name}字段审核`}>
          <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{field.display_name}</h3><div className="flex flex-wrap gap-2"><span className="badge">{changeLabels[chosen ? changeType(field.current_value, chosen.candidate_value) : field.change_type]}</span><span className="badge">{decisionLabels[field.decision] ?? field.decision}</span>{field.verification_state ? <span className="badge">{fieldReviewFlagLabels[chosen?.source?.verification_state ?? field.verification_state] ?? ((chosen?.source?.verification_state ?? field.verification_state) === "VERIFIED" ? "人工核验通过" : field.verification_state)}</span> : null}</div></div>
          <div className="mt-4 grid gap-3 sm:grid-cols-2"><ValueBlock label="当前正式值" value={field.current_value} /><ValueBlock label={chosen ? "已选候选值" : "候选值（尚未选择）"} value={chosen ? chosen.candidate_value : field.candidate_value} /></div>
          <p className="mt-2 text-xs text-muted">正式值最近核验：{time(field.last_verified_at)}。空缺的旧核验时间与核验人不会自动补齐。</p>
          <div className="mt-4 space-y-3">
            {field.proposals.map((proposal, index) => <div key={proposal.id} className="panel-soft min-w-0 p-4">
              <label className="flex items-start gap-2 text-sm font-medium"><input className="mt-1" type="radio" name={`${row.id}-${field.field_name}-proposal`} aria-label={`采用${field.display_name}候选 ${index + 1}`} checked={selection.proposalId === proposal.id} disabled={settled} onChange={() => choose(field.field_name, { proposalId: proposal.id, confirmDelete: false })} /><span className="min-w-0 whitespace-pre-wrap break-words">候选 {index + 1}：{reviewValue(proposal.candidate_value)}</span></label>
              <SourceDetails source={proposal.source} config={config} />
              {!learning.blind ? <p className="mt-2 text-xs text-muted">置信度：{proposal.confidence == null ? "未提供" : `${Math.round(proposal.confidence * 100)}%`}（仅供参考）</p> : null}
              {!verified(proposal.source) && !settled ? <button type="button" aria-label={`核验来源 ${proposal.id}`} disabled={!note.trim() || !proposal.source || !(proposal.source.source_url || (proposal.source.source_title && proposal.source.publisher))} className="button-secondary mt-3 text-xs" onClick={() => act(() => verifyFieldReviewSource(row.id, proposal.id, row.preview_token, note.trim()), "来源核验已保存，请基于新预览选择要处理的字段。")}>已核对原始材料，记录来源核验</button> : null}
            </div>)}
          </div>
          {(field.timeline?.length || field.timeline_total) ? <FieldSourceTimeline key={row.preview_token + field.field_name} candidateId={row.id} field={field} config={config} onSelect={onSelect} /> : null}
          {field.conflicts?.length ? <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3"><h4 className="text-sm font-semibold text-amber-900">{field.risk_reasons?.includes("CONFLICT") ? "其他待审候选的冲突值" : "其他待审候选的来源值 / 一致证据"}</h4>{field.conflicts.map((conflict) => <div key={`${conflict.candidate_id}-${conflict.proposal_id}`} className="mt-3"><p className="whitespace-pre-wrap break-words text-sm">候选 #{conflict.candidate_id}：{reviewValue(conflict.candidate_value)}</p><SourceDetails source={conflict.source} config={config} /><Link className="mt-1 inline-block text-sm text-accent underline" href={`/admin/field-review?candidate=${conflict.candidate_id}`} onClick={(event) => { if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) { event.preventDefault(); onSelect(conflict.candidate_id); } }}>查看此冲突候选</Link></div>)}</div> : null}
          {!settled ? <div className="mt-4 space-y-3"><label className="grid gap-2 text-sm">{field.display_name}的处理方式<select className="field" value={selection.action ?? ""} onChange={(e) => choose(field.field_name, { action: (e.target.value || undefined) as ReviewDecision["action"] | undefined })}><option value="">暂不选择，保留待处理</option><option value="approve">批准选中的候选值</option><option value="reject">拒绝候选，保留正式值</option><option value="defer">暂缓，等待更多材料</option></select></label>
            {selection.action === "approve" && (!chosen || !verified(chosen.source)) ? <p className="text-sm text-amber-800">批准前，请明确选择一个候选值并完成该来源的人工核验。</p> : null}
            {selection.action === "approve" && needsDelete ? <label className="flex items-center gap-2 text-sm text-red-700"><input type="checkbox" checked={selection.confirmDelete ?? false} onChange={(e) => choose(field.field_name, { confirmDelete: e.target.checked })} />确认删除{field.display_name}的正式值</label> : null}
          </div> : null}
        </section>;
      })}
      <div className="panel p-5"><label className="grid gap-2 text-sm">审核意见<textarea className="field min-h-24 py-2" placeholder="记录核对的材料、采用此候选值的理由或暂缓原因" value={note} onChange={(e) => setNote(e.target.value)} /></label><p className="mt-3 text-sm text-muted">本次选择 {decisions.length} 个字段。其他字段继续保留原状态。来源核验后，请根据刷新后的预览重新选择。</p><button type="button" className="button-primary mt-3" disabled={!note.trim() || !decisions.length || invalid || !learning.canSubmit(row.id)} onClick={() => act(() => decideFieldReview(row.id, row.preview_token, note.trim(), decisions, learning.enabled ? learning.entries[row.id]?.session?.session_id : undefined), "字段审核已保存；未选择的字段继续待处理。", true)}>{busy ? "正在保存…" : "提交字段审核"}</button></div>
      {!learning.blind && row.bulk_eligible_fields.length && row.risk_level !== "HIGH_RISK" ? <div className="panel p-5"><h3 className="font-semibold">可批量批准的低风险字段</h3><p className="mt-2 text-sm text-muted">仅限当前候选内，后端确认同来源、已核验、无冲突且不覆盖已有值的字段。</p><div className="mt-3 flex flex-wrap gap-4">{row.bulk_eligible_fields.map((name) => <label key={name} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={batch.includes(name)} onChange={(e) => setBatch((fields) => e.target.checked ? [...fields, name] : fields.filter((field) => field !== name))} />{row.fields.find((field) => field.field_name === name)?.display_name ?? name}</label>)}</div><button type="button" className="button-secondary mt-4" disabled={!note.trim() || !batch.length} onClick={() => act(() => bulkApproveFieldReview(row, batch, note.trim()), "选中的低风险字段已批准。", true)}>批量批准低风险字段</button></div> : null}
    </fieldset>}
    <section aria-label="审核历史" className="panel p-5"><h3 className="font-semibold">审核历史</h3>{row.history.length ? <ol className="mt-4 space-y-4">{row.history.map((item, index) => <li key={index} className="border-t border-line pt-4 first:border-0 first:pt-0"><p className="text-sm font-medium">审核人 {item.reviewer_id ?? "未记录"} · {time(item.reviewed_at)}</p><p className="mt-2 whitespace-pre-wrap break-words text-sm">{item.note || "未填写意见"}</p><p className="mt-1 text-xs text-muted">{item.action === "field_reject_unstructured" ? "原始材料审核" : item.action ?? "字段审核"}{item.decisions?.length ? ` · ${item.decisions.map((decision) => decision.action === "reject_unstructured" ? "原始材料：拒绝" : `${row.fields.find((field) => field.field_name === decision.field_name)?.display_name ?? decision.field_name ?? "字段"}：${decision.action === "approve" ? "批准" : decision.action === "reject" ? "拒绝" : "暂缓"}`).join("；")}` : ""}</p><details className="mt-2 text-sm"><summary className="cursor-pointer text-accent">查看审核前后与来源记录</summary><div className="mt-3 grid gap-3 sm:grid-cols-2"><ValueBlock label="审核前" value={item.before} /><ValueBlock label="审核后" value={item.after} /></div><pre className="mt-3 whitespace-pre-wrap break-words text-xs">{reviewValue(item.sources)}</pre></details></li>)}</ol> : <p className="mt-3 text-sm text-muted">暂无审核记录。</p>}</section>
  </article>;
}

function ValueBlock({ label, value }: { label: string; value: unknown }) { return <div className="min-w-0 rounded-lg border border-line bg-slate-50 p-3"><p className="mb-2 text-xs text-muted">{label}</p><pre className="whitespace-pre-wrap break-words font-sans text-sm">{reviewValue(value)}</pre></div>; }
function SourceDetails({ source, config }: { source?: ReviewSource | null; config: FieldReviewConfig }) {
  const learning = useReviewLearning();
  if (!source) return <p className="mt-3 text-sm text-amber-800">缺少来源 · 尚不能批准</p>;
  const safeUrl = source.source_url && /^https?:\/\//i.test(source.source_url) ? source.source_url : null;
  return <div className="mt-3 space-y-1 break-words text-xs text-muted"><p>{config.source_types.find((item) => item.value === source.source_type)?.label ?? source.source_type ?? "来源类型未记录"} · {source.source_title || "标题未记录"} · 发布机构：{source.publisher || "未记录"}</p><p>发布时间：{time(source.published_at)} · 采集时间：{time(source.collected_at)}</p><p>可达性：{source.availability?.status || source.access_status || "UNKNOWN"}{source.source_failure_reason ? " · " + source.source_failure_reason : ""} · 访问观察时间：{time(source.availability?.checked_at || source.accessed_at || source.fetched_at)}</p>{source.evidence_notes ? <p className="whitespace-pre-wrap">证据片段：{reviewDisplayNotes(source.evidence_notes, learning.blind)}</p> : null}<p>{verified(source) ? "人工核验通过" : source.verification_state === "NO_SOURCE" ? "缺少可追踪来源，尚不能批准" : "来源未核验"} · 核验时间：{time(source.verified_at)} · 核验人：{source.verified_by ?? "未记录"}</p>{safeUrl ? <a className="inline-block break-all text-accent underline" href={safeUrl} target="_blank" rel="noopener noreferrer">打开来源原文：{safeUrl}</a> : <p>来源网址：{source.source_url || "未提供"}</p>}</div>;
}

function FieldSourceTimeline({ candidateId, field, config, onSelect }: { candidateId: number; field: ReviewField; config: FieldReviewConfig; onSelect: (id: number) => void }) {
  const [more, setMore] = useState<ReviewTimelineEntry[]>([]);
  const [total, setTotal] = useState(field.timeline_total ?? field.timeline?.length ?? 0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const loaded = [...(field.timeline ?? []), ...more];
  async function loadMore() {
    setBusy(true); setError("");
    try { const result = await fieldReviewSources(candidateId, field.field_name, loaded.length); setMore((items) => [...items, ...result.items]); setTotal(result.total); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "来源加载失败，请重试。"); }
    finally { setBusy(false); }
  }
  const stamp = (value?: string | null) => value && Number.isFinite(Date.parse(value)) ? Date.parse(value) : Number.POSITIVE_INFINITY;
  const entries = [...loaded].sort((a, b) => stamp(a.source?.published_at) - stamp(b.source?.published_at));
  return <section aria-label={field.display_name + "来源时间线"} className="mt-4 rounded-lg border border-blue-200 bg-blue-50/30 p-4">
    <h4 className="font-semibold">来源时间线 · 已显示 {loaded.length} / {total} 条</h4><p className="mt-1 text-xs text-muted">按原文发布时间排列，缺少时间的材料置后。后续、延期或更正提示不自动决定采用哪个值。</p>
    <ol className="mt-3 space-y-4">{entries.map((item, index) => <li key={item.candidate_id + "-" + item.proposal_id + "-" + index} className="border-l-2 border-line pl-3">
      <p className="whitespace-pre-wrap break-words text-sm">{reviewValue(item.candidate_value)}</p>
      <p className="mt-1 text-xs text-muted">候选 #{item.candidate_id} · 范围：{typeof item.scope === "string" ? item.scope : item.scope ? JSON.stringify(item.scope) : "当前字段"}</p>
      {item.announcement_hint ? <p className="mt-1 text-xs text-amber-800">{typeof item.announcement_hint === "string" ? item.announcement_hint : "可能为后续或更正材料，请核对正文"}</p> : null}
      <SourceDetails source={item.source} config={config} />
      <button type="button" className="mt-2 text-xs text-accent underline" onClick={() => onSelect(item.candidate_id)}>查看候选 #{item.candidate_id}</button>
    </li>)}</ol>
    {error ? <p role="alert" className="mt-3 text-sm text-red-700">{error}</p> : null}
    {loaded.length < total ? <button type="button" className="button-secondary mt-3" disabled={busy} onClick={loadMore}>{busy ? "正在加载来源…" : "查看更多来源"}</button> : null}
  </section>;
}
