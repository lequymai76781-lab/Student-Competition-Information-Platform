"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { DocumentClassification } from "@/components/DocumentClassification";
import { PageHeader } from "@/components/PageHeader";
import { SessionBoundary } from "@/components/v09/SessionBoundary";
import { analyzePolicy, confirmPolicyMatch, documentExplanation, documentStatusLabel, documentTypeLabels, getDocumentClassifications, getPolicyAnalyses, replayDocumentClassifications, type ClassificationItem, type PolicyAnalysisEntry, type PolicyItem } from "@/lib/document-policy-api";
import { usePrivateResource } from "@/lib/use-private-resource";
import { useSessionToken } from "@/lib/use-session";

function sourceLink(url?: string | null, label = "查看来源原文") {
  if (!url || !/^https?:\/\//i.test(url)) return <span className="text-xs text-muted">来源网址未提供或不可打开</span>;
  return <a className="break-all text-sm text-accent underline" href={url} target="_blank" rel="noopener noreferrer">{label}</a>;
}
function score(value?: number | null) { return value == null ? "未提供" : `${Math.round(value * 100)}%`; }
function status(value?: string | null) {
  return value ? documentStatusLabel(value) : "未记录";
}

function PolicyMatchConfirmation({ policyId, entry, onUpdated }: { policyId: number; entry: PolicyAnalysisEntry; onUpdated: () => void }) {
  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const candidates = [...new Set((entry.candidate_ids ?? []).filter((id) => Number.isSafeInteger(id) && id > 0))];
  if (entry.match_status !== "NEEDS_QUICK_CONFIRM" || !candidates.length) return null;
  async function confirm() {
    if (busy || !selected || !reason.trim()) return;
    setBusy(true); setError("");
    try { await confirmPolicyMatch(policyId, entry.raw_competition_name, Number(selected), reason.trim()); onUpdated(); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "赛事匹配确认失败，请重试。"); }
    finally { setBusy(false); }
  }
  return <div className="mt-3 space-y-2 rounded-lg border border-amber-200 p-3">
    <p className="text-xs text-muted">仅确认这条政策中的赛事名称；政策来源、范围和有效期仍由服务器核验。</p>
    <label className="grid gap-1">匹配赛事 ID<select className="field" value={selected} disabled={busy} onChange={(event) => setSelected(event.target.value)}><option value="">选择待确认赛事</option>{candidates.map((id) => <option key={id} value={id}>赛事 #{id}</option>)}</select></label>
    <label className="grid gap-1">匹配确认依据<textarea className="field min-h-20 py-2" value={reason} disabled={busy} onChange={(event) => setReason(event.target.value)} /></label>
    <button type="button" className="button-secondary" disabled={busy || !selected || !reason.trim()} onClick={() => void confirm()}>确认赛事匹配</button>
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
  </div>;
}

export default function DocumentPolicyPage() { return <SessionBoundary><DocumentPolicyContent /></SessionBoundary>; }

function DocumentPolicyContent() {
  const router = useRouter();
  const token = useSessionToken();
  const [sourcePage, setSourcePage] = useState(0);
  const [policyPage, setPolicyPage] = useState(0);
  const [tab, setTab] = useState<"classifications" | "policies">("classifications");
  const [updated, setUpdated] = useState<Record<number, ClassificationItem["classification"]>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const loadClassifications = useCallback(() => getDocumentClassifications(sourcePage * 50), [sourcePage]);
  const loadPolicies = useCallback(() => getPolicyAnalyses(policyPage * 50), [policyPage]);
  const classifications = usePrivateResource(`document-policy-classifications-${sourcePage}`, loadClassifications);
  const policies = usePrivateResource(`document-policy-policies-${policyPage}`, loadPolicies);
  useEffect(() => {
    if (!token && !window.localStorage.getItem("v09_token")) router.replace("/login?next=%2Fadmin%2Fdocument-policy");
  }, [token, router]);
  async function replay() {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try { await replayDocumentClassifications(); classifications.reload(); setMessage("分类回放已完成，列表正在刷新。"); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "分类回放失败，请重试。"); }
    finally { setBusy(false); }
  }
  async function analyze(item: PolicyItem) {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try {
      await analyzePolicy(item.id);
      policies.reload(); setMessage(`政策「${item.title}」分析已完成。`);
    } catch (exc) { setError(exc instanceof Error ? exc.message : "政策分析失败，请重试。"); }
    finally { setBusy(false); }
  }
  if (!token) return null;
  return <>
    <PageHeader eyebrow="文档与政策" title="来源文档分类与政策分析" description="系统识别一级分类，二级标签仅供参考；字段事实与政策关系分别审核。" action={<Link href="/admin/field-review" className="button-secondary">返回字段审核</Link>} />
    <main className="container-page space-y-5 py-8">
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="文档政策视图">
        <button type="button" role="tab" aria-selected={tab === "classifications"} className={tab === "classifications" ? "button-primary" : "button-secondary"} onClick={() => { setTab("classifications"); setError(""); }}>来源分类</button>
        <button type="button" role="tab" aria-selected={tab === "policies"} className={tab === "policies" ? "button-primary" : "button-secondary"} onClick={() => { setTab("policies"); setError(""); }}>政策分析结果</button>
      </div>
      {error ? <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
      {message ? <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{message}</p> : null}
      {tab === "classifications" ? <section aria-label="来源分类列表" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">来源分类（共 {classifications.data?.total ?? 0} 条）</h2><button type="button" className="button-secondary" disabled={busy} onClick={() => void replay()}>回放已保存材料分类</button></div>
        {classifications.error ? <p role="alert" className="text-sm text-red-700">{classifications.error}</p> : null}
        {!classifications.ready ? <p role="status" className="text-sm text-muted">正在加载来源分类…</p> : null}
        {classifications.data?.statistics ? <p className="text-xs text-muted">系统自动分类 {classifications.data.statistics.AUTO_CLASSIFIED ?? 0} 条；字段和关系的待审任务单独处理。</p> : null}
        {classifications.data?.items.map((item) => <article key={item.id} className="panel space-y-3 p-5"><div><h3 className="font-semibold">{item.title}</h3><p className="text-xs text-muted">候选 #{item.id} · {item.school_name || "学校未记录"} · {item.competition_name || "赛事未记录"} · {status(item.status)}</p></div>
          {sourceLink(item.source_url)}
          {item.relation_evidence?.relation_type === "participation_evidence" ? <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm"><p>已保存学校参赛证据；仅作为参赛证据，不代表正式政策认可。</p>{sourceLink(item.relation_evidence.source_url || item.source_url, "查看参赛证据来源")}</div> : null}
          {(updated[item.id] ?? item.classification) ? <DocumentClassification key={`${item.id}-${(updated[item.id] ?? item.classification)?.document_type}`} candidateId={item.id} classification={(updated[item.id] ?? item.classification)!} documentTypes={classifications.data?.document_types} onUpdated={(value) => setUpdated((previous) => ({ ...previous, [item.id]: value }))} /> : <p className="text-sm text-amber-800">尚无系统分类，需人工核对来源。</p>}
        </article>)}
        {classifications.data && !classifications.data.items.length ? <p className="text-sm text-muted">暂无已保存的来源材料。</p> : null}
        {classifications.data && classifications.data.total > 50 ? <div className="flex items-center gap-3 text-sm"><button type="button" className="button-secondary" disabled={sourcePage === 0} onClick={() => setSourcePage((value) => value - 1)}>上一页来源</button><span>第 {sourcePage + 1} 页</span><button type="button" className="button-secondary" disabled={(sourcePage + 1) * 50 >= classifications.data.total} onClick={() => setSourcePage((value) => value + 1)}>下一页来源</button></div> : null}
      </section> : <section aria-label="政策分析列表" className="space-y-4">
        <h2 className="text-lg font-semibold">政策分析（共 {policies.data?.total ?? 0} 条）</h2>
        {policies.error ? <p role="alert" className="text-sm text-red-700">{policies.error}</p> : null}
        {!policies.ready ? <p role="status" className="text-sm text-muted">正在加载政策分析…</p> : null}
        {policies.data?.items.map((item) => {
          const analysis = item.analysis;
          return <article key={item.id} className="panel space-y-3 p-5"><div><h3 className="font-semibold">{item.title}</h3><p className="text-xs text-muted">政策 #{item.id} · {item.school_name || `学校 #${item.university_id ?? "未记录"}`}</p></div>
            {sourceLink(item.source_url, "查看政策原文")}
            {item.classification ? <DocumentClassification classification={item.classification} /> : null}
            <button type="button" className="button-secondary" disabled={busy} onClick={() => void analyze(item)}>分析政策 {item.title}</button>
            {analysis ? <div className="space-y-3"><p className="text-sm">已自动建立关系 {analysis.automatic_relations} 条 · 人工确认关系 {analysis.human_confirmed_relations ?? 0} 条 · {analysis.requires_human_confirmation ? "仍需人工确认" : "无待确认项"}</p>
              {analysis.blocking_reasons?.length ? <div className="text-sm text-amber-800"><strong>自动处理受阻：</strong><ul className="list-inside list-disc">{analysis.blocking_reasons.map((reason, index) => <li key={index}>{documentExplanation(reason)}</li>)}</ul></div> : null}
              {analysis.conflicts?.length ? <p className="text-sm text-red-700">检测到 {analysis.conflicts.length} 项冲突，需人工处理。</p> : null}
              {analysis.entries?.map((entry, index) => <section key={`${entry.raw_competition_name}-${index}`} aria-label={`政策条目 ${entry.raw_competition_name}`} className="rounded-lg border border-line p-3 text-sm">
                <h4 className="font-medium">{entry.raw_competition_name}</h4>
                <p>规范名称：{entry.normalized_name || "未确定"} · 认可类型：{documentTypeLabels[entry.recognition_type ?? ""] ?? "待核对"}</p>
                <p>匹配：{status(entry.match_status)}（{score(entry.match_confidence)}）{entry.matched_competition_id ? ` · 赛事 #${entry.matched_competition_id}` : ""}</p>
                <p>关系：{status(entry.relation_status)} · 核验方式：{status(entry.verification_method)}</p>
                {entry.match_reason ? <p>匹配依据：{documentExplanation(entry.match_reason)}</p> : null}
                {entry.evidence_text ? <p className="whitespace-pre-wrap">原文证据：{entry.evidence_text}</p> : null}
                {entry.locator ? <p>证据位置：{entry.locator}</p> : null}
                <p>来源：{entry.source_title || item.title} · {sourceLink(entry.source_url || item.source_url, "查看政策原文")}</p>
                <p>有效期：{entry.effective_from || "未记录"} 至 {entry.effective_to || "未记录"}</p>
                {entry.blocking_reasons?.length ? <p className="text-amber-800">人工处理原因：{entry.blocking_reasons.map(documentExplanation).join("；")}</p> : null}
                <PolicyMatchConfirmation policyId={item.id} entry={entry} onUpdated={policies.reload} />
              </section>)}
            </div> : <p className="text-sm text-muted">尚无分析结果。需明确点击“分析政策”。</p>}
          </article>;
        })}
        {policies.data && !policies.data.items.length ? <p className="text-sm text-muted">暂无政策文档。</p> : null}
        {policies.data && policies.data.total > 50 ? <div className="flex items-center gap-3 text-sm"><button type="button" className="button-secondary" disabled={policyPage === 0} onClick={() => setPolicyPage((value) => value - 1)}>上一页政策</button><span>第 {policyPage + 1} 页</span><button type="button" className="button-secondary" disabled={(policyPage + 1) * 50 >= policies.data.total} onClick={() => setPolicyPage((value) => value + 1)}>下一页政策</button></div> : null}
      </section>}
    </main>
  </>;
}
