"use client";

import Link from "next/link";
import { reviewDisplayFlags, reviewDisplayTitle } from "@/lib/review-learning-display";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { ReviewLearningProvider, useReviewLearning } from "@/components/ReviewLearning";
import { PageHeader } from "@/components/PageHeader";
import { ReviewStatisticsPanel, ReviewTimingControls, ReviewTimingProvider } from "@/components/ReviewTelemetry";
import { FieldReviewBatch } from "@/components/FieldReviewBatch";
import { FieldReviewCandidateForm } from "@/components/FieldReviewCandidateForm";
import { FieldReviewDetail, fieldReviewFlagLabels, fieldReviewStatusLabels } from "@/components/FieldReviewDetail";
import { Pagination } from "@/components/v09/Pagination";
import { SessionBoundary } from "@/components/v09/SessionBoundary";
import { fieldReview, fieldReviewConfig, fieldReviews, type FieldReview, type FieldReviewFilters } from "@/lib/field-review-api";
import { formatDate } from "@/lib/format";
import { usePrivateResource } from "@/lib/use-private-resource";
import { useSessionToken } from "@/lib/use-session";

const pageSize = 20;
const defaultFilters: FieldReviewFilters = { status: "pending" };
export default function FieldReviewPage() { return <SessionBoundary><ReviewLearningProvider><ReviewTimingProvider><FieldReviewSession /></ReviewTimingProvider></ReviewLearningProvider></SessionBoundary>; }

function FieldReviewSession() {
  const learning = useReviewLearning();
  const router = useRouter();
  const token = useSessionToken();
  const [draftFilters, setDraftFilters] = useState<FieldReviewFilters>(defaultFilters);
  const [filters, setFilters] = useState<FieldReviewFilters>(defaultFilters);
  const [page, setPage] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [batchRows, setBatchRows] = useState<FieldReview[]>([]);
  const [form, setForm] = useState<"new" | "prepare" | null>(null);
  const [message, setMessage] = useState("");
  const [statsRevision, setStatsRevision] = useState(0);
  const loadQueue = useCallback(async () => {
    const visibleFilters = learning.blind ? { ...filters, risk: undefined, relation_type: undefined, flag: reviewDisplayFlags(filters.flag ? [filters.flag] : [], true)[0], sort: filters.sort === "priority" ? "newest" : filters.sort } : filters;
    return { queue: await fieldReviews(visibleFilters, pageSize, page * pageSize) };
  }, [filters, page, learning.blind]);
  const configResource = usePrivateResource("field-review-config", fieldReviewConfig);
  const queue = usePrivateResource(JSON.stringify([filters, page]), loadQueue);
  const loadDetail = useCallback(() => selectedId == null ? Promise.resolve(null) : fieldReview(selectedId), [selectedId]);
  const detail = usePrivateResource(`field-review-${selectedId}`, loadDetail);
  useEffect(() => {
    if (!token && !window.localStorage.getItem("v09_token")) router.replace("/login?next=%2Fadmin%2Ffield-review");
  }, [token, router]);
  useEffect(() => {
    const sync = () => {
      const raw = new URLSearchParams(window.location.search).get("candidate");
      setSelectedId(raw && /^[1-9]\d*$/.test(raw) && Number.isSafeInteger(Number(raw)) ? Number(raw) : null);
      setForm(null);
    };
    sync(); window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  function select(id: number) {
    setSelectedId(id); setForm(null); setMessage("");
    const url = new URL(window.location.href); url.searchParams.set("candidate", String(id));
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }
  function refresh() { detail.reload(); queue.reload(); setStatsRevision((value) => value + 1); }
  function refreshQueue() { queue.reload(); setStatsRevision((value) => value + 1); }
  function updateSelected(row: FieldReview) { setBatchRows((rows) => rows.map((item) => item.id === row.id ? row : item)); }
  function toggleBatch(row: FieldReview, checked: boolean) { setBatchRows((rows) => checked ? (rows.length < 50 && !rows.some((item) => item.id === row.id) ? [...rows, row] : rows) : rows.filter((item) => item.id !== row.id)); }
  function saved(row: FieldReview) { select(row.id); setMessage("候选已保存，等待人工核验与字段审核。"); refresh(); }
  function changeFilter(key: keyof FieldReviewFilters, value: string) { setDraftFilters((previous) => ({ ...previous, [key]: value })); }
  const config = configResource.data;
  const current = detail.data;
  if (!token) return null;
  return <>
    <PageHeader eyebrow="Field Review" title="赛事字段审核" description="逐项核对赛事与届次资料，明确选择需要批准、拒绝或暂缓的字段。" icon={ShieldCheck} action={<Link href="/admin/review" className="button-secondary">返回审核中心</Link>} />
    <section className="container-page space-y-6 py-8">
      <ReviewStatisticsPanel revision={statsRevision} />
      <ReviewTimingControls />
      {message ? <p role="status" className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">{message}</p> : null}
      <form className="panel p-4" aria-label="字段审核筛选" onSubmit={(event) => { event.preventDefault(); setFilters({ ...draftFilters, created_from: draftFilters.created_from ? `${draftFilters.created_from}T00:00:00+08:00` : undefined, created_to: draftFilters.created_to ? `${draftFilters.created_to}T23:59:59.999+08:00` : undefined }); setPage(0); setMessage(""); }}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
<label className="grid gap-1 text-sm">搜索候选<input className="field" type="search" value={draftFilters.search ?? ""} onChange={(e) => changeFilter("search", e.target.value)} placeholder="赛事、学校、材料或来源" /></label>
{!learning.blind ? <label className="grid gap-1 text-sm">风险筛选<select className="field" value={draftFilters.risk ?? ""} onChange={(e) => changeFilter("risk", e.target.value)}><option value="">全部风险</option><option value="LOW_RISK">低风险</option><option value="HIGH_RISK">高风险 · 逐条审核</option></select></label> : null}
{!learning.blind ? <label className="grid gap-1 text-sm">关系类型筛选<select className="field" value={draftFilters.relation_type ?? ""} onChange={(e) => changeFilter("relation_type", e.target.value)}><option value="">全部材料类型</option>{Object.entries({ registration_notice: "报名通知", organization_notice: "组织参赛", selection_notice: "校内选拔", recommendation_notice: "推荐参赛", policy_recognition: "正式认定政策", award_policy: "奖励政策", repost: "转载材料", other: "其他材料", competition_notice: "赛事通知" }).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label> : null}
<label className="grid gap-1 text-sm">队列排序<select className="field" value={draftFilters.sort ?? "newest"} onChange={(e) => changeFilter("sort", e.target.value)}><option value="newest">最新提交</option><option value="oldest">最早提交</option>{!learning.blind ? <option value="priority">风险优先</option> : null}</select></label>

          <label className="grid gap-1 text-sm">队列状态<select className="field" value={draftFilters.status ?? "pending"} onChange={(e) => changeFilter("status", e.target.value)}>{["pending", "partially_approved", "deferred", "approved", "rejected", "all"].map((value) => <option key={value} value={value}>{fieldReviewStatusLabels[value] ?? "全部状态"}</option>)}</select></label>
          <label className="grid gap-1 text-sm">待办标记<select className="field" value={draftFilters.flag ?? ""} onChange={(e) => changeFilter("flag", e.target.value)}><option value="">全部标记</option>{Object.entries(fieldReviewFlagLabels).filter(([value]) => ["CONFLICT", "NO_SOURCE", "UNVERIFIED", "DUPLICATE_SUSPECTED", "edition_uncertain", "LOW_RISK", "HIGH_RISK", "RELATION_CONFLICT"].includes(value) && reviewDisplayFlags([value], learning.blind).length > 0).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label className="grid gap-1 text-sm">实体类型筛选<select className="field" value={draftFilters.entity_type ?? ""} onChange={(e) => changeFilter("entity_type", e.target.value)}><option value="">全部实体</option><option value="competition">赛事本体</option><option value="edition">具体届次</option></select></label>
          <label className="grid gap-1 text-sm">来源类型筛选<select className="field" value={draftFilters.source_type ?? ""} onChange={(e) => changeFilter("source_type", e.target.value)}><option value="">全部来源</option>{config?.source_types.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label className="grid gap-1 text-sm">赛事 ID 筛选<input className="field" type="number" min="1" step="1" value={draftFilters.competition_id ?? ""} onChange={(e) => changeFilter("competition_id", e.target.value)} /></label>
          <label className="grid gap-1 text-sm">学校 ID 筛选<input className="field" type="number" min="1" step="1" value={draftFilters.university_id ?? ""} onChange={(e) => changeFilter("university_id", e.target.value)} /></label>
          <label className="grid gap-1 text-sm">提交人 ID 筛选<input className="field" type="number" min="1" step="1" value={draftFilters.submitter_id ?? ""} onChange={(e) => changeFilter("submitter_id", e.target.value)} /></label>
          <label className="grid gap-1 text-sm">提交日期从<input className="field" type="date" value={draftFilters.created_from ?? ""} onChange={(e) => changeFilter("created_from", e.target.value)} /></label>
          <label className="grid gap-1 text-sm">提交日期至<input className="field" type="date" value={draftFilters.created_to ?? ""} onChange={(e) => changeFilter("created_to", e.target.value)} /></label>
        </div>
        <div className="mt-4 flex flex-wrap gap-3"><button type="submit" className="button-secondary">应用筛选</button><button type="button" className="button-secondary" onClick={() => { setDraftFilters(defaultFilters); setFilters(defaultFilters); setPage(0); }}>重置筛选</button><button type="button" className="button-primary" disabled={!config} onClick={() => { setForm("new"); setMessage(""); }}>新建候选</button></div>
      </form>
      {configResource.error ? <div role="alert" className="panel p-4 text-sm text-red-700">{configResource.error}<button type="button" className="ml-3 underline" onClick={configResource.reload}>重新加载审核配置</button></div> : null}
      {queue.error ? <div role="alert" className="panel p-4 text-sm text-red-700">{queue.error}<button type="button" onClick={queue.reload} className="ml-3 underline">重新加载队列</button></div> : null}
      {!queue.ready ? <p role="status" className="text-sm text-muted">正在加载字段审核队列…</p> : null}
      {queue.data ? <section aria-label="字段候选队列" className="panel p-4"><h2 className="font-semibold">候选队列 <span className="font-normal text-muted">（共 {queue.data.queue.total} 条）</span></h2><div className="mt-3 grid gap-3 md:grid-cols-2">{queue.data.queue.items.map((row) => <div key={row.id} className="min-w-0 rounded-lg border border-line"><label className="flex items-center gap-2 px-4 pt-3 text-xs"><input type="checkbox" aria-label={"选择候选 " + row.id} checked={batchRows.some((item) => item.id === row.id)} disabled={learning.blind || row.risk_level !== "LOW_RISK" || row.collection_context?.kind === "school_mapping" || !(row.low_risk_fields ?? []).length || (batchRows.length >= 50 && !batchRows.some((item) => item.id === row.id))} onChange={(e) => toggleBatch(row, e.target.checked)} />{learning.blind ? "逐条独立审核" : row.risk_level === "LOW_RISK" ? "低风险 · 可加入摘要" : row.risk_level === "HIGH_RISK" ? "高风险 · 逐条审核" : "逐条核对"}</label><button type="button" aria-label={`查看候选 ${reviewDisplayTitle(row, learning.blind)}`} aria-pressed={selectedId === row.id} onClick={() => select(row.id)} className={`w-full min-w-0 rounded-lg border-0 p-4 text-left ${selectedId === row.id ? "border-blue-300 bg-blue-50" : "border-line bg-white"}`}><span className="block break-words font-medium">{reviewDisplayTitle(row, learning.blind)}</span><span className="mt-2 block text-xs text-muted">#{row.id} · {row.entity_type === "edition" ? `${row.year ?? "待定"} 届次` : "赛事本体"} · {fieldReviewStatusLabels[row.status] ?? row.status} · {formatDate(row.created_at)}</span><span className="mt-2 block text-xs text-amber-800">{reviewDisplayFlags(row.flags, learning.blind).map((flag) => fieldReviewFlagLabels[flag] ?? flag).join(" · ") || "无待办标记"}</span>{reviewDisplayFlags(row.risk_reasons, learning.blind).length ? <span className="mt-2 block text-xs text-amber-800">{reviewDisplayFlags(row.risk_reasons, learning.blind).map((reason) => fieldReviewFlagLabels[reason] ?? reason).join(" · ")}</span> : null}</button></div>)}</div>{!queue.data.queue.items.length ? <p className="mt-4 text-sm text-muted">当前条件下暂无候选，可调整筛选或新建候选。</p> : null}<Pagination label="字段候选分页" page={page} hasNext={(page + 1) * pageSize < queue.data.queue.total} disabled={!queue.ready} onPage={setPage} /></section> : null}
      {learning.blind ? <p className="text-sm text-muted">独立盲审需要逐条选择人工类型，当前不提供批量审核。<Link href="/admin/review-learning" className="ml-2 text-accent underline">学习状态</Link></p> : <FieldReviewBatch selected={batchRows} sourceTypes={config?.source_types} onRemove={(id) => setBatchRows((rows) => rows.filter((row) => row.id !== id))} onClear={() => setBatchRows([])} onCompleted={(text) => { setMessage(text); refresh(); }} onSelect={select} />}
      {form && config && (form === "new" || current) ? <FieldReviewCandidateForm key={form === "prepare" ? `prepare-${current?.id}-${current?.preview_token}` : "new"} config={config} initial={form === "prepare" ? current ?? undefined : undefined} onSaved={saved} onCancel={() => setForm(null)} /> : null}
      {!form && selectedId != null ? <>
        {!detail.ready ? <p role="status" className="text-sm text-muted">正在加载候选详情…</p> : null}
        {detail.error ? <div role="alert" className="panel p-4 text-sm text-red-700">{detail.error}<button type="button" onClick={detail.reload} className="ml-3 underline">重新加载详情</button></div> : null}
        {current && config ? <FieldReviewDetail key={`${current.id}-${current.preview_token}`} row={current} config={config} onReload={refresh} onQueueReload={refreshQueue} onUpdated={updateSelected} onPrepare={() => setForm("prepare")} onMessage={setMessage} onSelect={select} /> : null}
      </> : null}
    </section>
  </>;
}
