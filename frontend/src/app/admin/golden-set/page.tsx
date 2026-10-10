"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { SessionBoundary } from "@/components/v09/SessionBoundary";
import { documentTypeLabels } from "@/lib/document-policy-api";
import { ApiError } from "@/lib/v09-api";
import { usePrivateResource } from "@/lib/use-private-resource";
import { useSessionToken } from "@/lib/use-session";
import {
  exposeGoldenPrediction, exportGoldenSet, getGoldenAudits, getGoldenMetrics, getGoldenSet, saveGoldenAnnotation, saveGoldenAudit,
  type AnnotationStatus, type Answer, type AuditAnnotation, type AuditItem, type AuditKind, type AuditSet,
  type GoldenAnnotation, type GoldenMetrics, type GoldenProgress, type GoldenSet, type GoldenSource,
} from "@/lib/golden-set-api";

type QueueKind = "sources" | AuditKind;
type QueueItem = GoldenSource | AuditItem;
type SavedAnnotation = GoldenAnnotation | AuditAnnotation;
type Draft = { primary: string; secondary: string[]; note: string; answers: Record<string, Answer>; informationalSafe: Answer | ""; revision: number; dirty: boolean };
type TypeOption = { value: string; label: string };
const shortcuts: Record<string, string> = { "1": "registration_notice", "2": "organization_notice", "3": "selection_notice", "4": "result_notice", "5": "publicity_notice", "6": "completion_news", "7": "competition_intro", "8": "policy_recognition_document", "9": "other" };
const informationalTypes = new Set(["completion_news", "competition_intro", "event_news", "result_notice", "publicity_notice", "historical_material", "repost"]);
const labels = { sources: "分类标注", policies: "政策核验", relations: "关系核验" };
const answerLabels = { yes: "是", no: "否", unsure: "不确定" };
const dangerLabels: Record<string, string> = { notice_to_policy: "通知误判为政策", news_to_policy: "新闻误判为政策", registration_to_postgraduate: "报名通知误判为推免政策", result_or_news_to_comprehensive: "结果或新闻误判为综合测评政策" };
const entryLabels: Record<string, string> = { matched_competition_id: "匹配赛事 ID", publisher: "发布部门", published_at: "发布日期", raw_competition_name: "原文赛事名", normalized_name: "规范名称", competition_name: "匹配赛事", recognition_type: "认可类型", match_confidence: "匹配置信度", match_reason: "匹配依据", source_title: "来源标题", source_url: "来源网址", evidence_text: "证据原文", locator: "证据位置", effective_from: "开始日期", effective_to: "结束日期", relation_status: "关系状态", match_status: "匹配状态", blocking_reasons: "待核验原因" };
function itemId(item: QueueItem) { return String("source_id" in item ? item.source_id : item.audit_id); }
function makeDraft(annotation: SavedAnnotation | null): Draft {
  return { primary: annotation && "human_primary_type" in annotation ? annotation.human_primary_type ?? "" : "",
    secondary: annotation && "human_secondary_types" in annotation ? [...annotation.human_secondary_types] : [],
    note: annotation?.note ?? "", answers: annotation && "answers" in annotation ? { ...annotation.answers } : {},
    informationalSafe: annotation && "informational_safe" in annotation ? annotation.informational_safe ?? "" : "",
    revision: annotation?.revision ?? 0, dirty: false };
}
function sourceLink(url: string | null, label = "查看来源原文") {
  if (!url || !/^https?:\/\//i.test(url)) return <span className="text-sm text-muted">来源网址未提供或不可打开</span>;
  return <a className="break-all text-sm text-accent underline" href={url} target="_blank" rel="noopener noreferrer">{label}</a>;
}
function percent(value: unknown) { return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "暂无数据"; }
function record(value: unknown): Record<string, unknown> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {}; }
function display(value: unknown): string { return value == null ? "未提供" : typeof value === "object" ? JSON.stringify(value) : String(value); }
function errorMessage(error: unknown) { return error instanceof Error ? error.message : "操作失败，请重试。"; }
function Progress({ value }: { value: GoldenProgress }) {
  return <div className="space-y-2"><p className="text-sm font-medium">已完成 {value.annotated} / {value.total} · 服务端草稿 {value.draft} · 跳过 {value.skipped} · 未开始 {value.untouched}</p><progress aria-label="人工标注完成进度" className="h-2 w-full accent-blue-600" value={value.annotated} max={value.total || 1} /></div>;
}

export default function GoldenSetPage() { return <SessionBoundary><GoldenSetContent /></SessionBoundary>; }
function GoldenSetContent() {
  const token = useSessionToken();
  const router = useRouter();
  const dataset = usePrivateResource("golden-set", getGoldenSet);
  const [tab, setTab] = useState<QueueKind | "metrics">("sources");
  const [visited, setVisited] = useState<Partial<Record<AuditKind, boolean>>>({});
  useEffect(() => { if (!token && !window.localStorage.getItem("v09_token")) router.replace("/login?next=%2Fadmin%2Fgolden-set"); }, [token, router]);
  if (!token) return null;
  return <>
    <PageHeader eyebrow="Golden Set" title="人工标注工作台" description="先看原文，再选类型。只有明确保存的人工标注计入评估。" action={<Link href="/admin" className="button-secondary">返回管理台</Link>} />
    <main className="container-page space-y-5 py-6">
      <div role="tablist" aria-label="标注与评估" className="flex flex-wrap gap-2">
        {(["sources", "policies", "relations", "metrics"] as const).map((value) => <button key={value} type="button" role="tab" aria-selected={tab === value} className={tab === value ? "button-primary" : "button-secondary"} onClick={() => { setTab(value); if (value === "policies" || value === "relations") setVisited(previous => ({ ...previous, [value]: true })); }}>{value === "metrics" ? "评估与导出" : labels[value]}</button>)}
      </div>
      {dataset.error ? <div role="alert" className="panel p-4 text-red-700">{dataset.error}<button className="button-secondary ml-3" onClick={dataset.reload}>重新加载</button></div> : null}
      {!dataset.ready ? <p role="status">正在加载固定样本…</p> : null}
      {dataset.data ? <>
        <div hidden={tab !== "sources"}><Queue datasetId={dataset.data.dataset_id} kind="sources" initial={dataset.data.items} initialProgress={dataset.data.progress} documentTypes={dataset.data.document_types} checks={[]} active={tab === "sources"} /></div>
        {(["policies", "relations"] as const).map(kind => visited[kind] ? <div key={kind} hidden={tab !== kind}><AuditQueue datasetId={dataset.data!.dataset_id} kind={kind} active={tab === kind} /></div> : null)}
        {tab === "metrics" ? <Metrics /> : null}
        <p className="text-xs text-muted">数据集 {dataset.data.dataset_id} · 分类样本 {dataset.data.total} 条。分类、政策与关系分别核验，草稿和跳过不计入完成数。</p>
      </> : null}
    </main>
  </>;
}
function AuditQueue({ datasetId, kind, active }: { datasetId: string; kind: AuditKind; active: boolean }) {
  const load = useCallback(() => getGoldenAudits(kind), [kind]);
  const data = usePrivateResource(`golden-audits-${kind}`, load);
  return data.data ? <Queue datasetId={datasetId} kind={kind} initial={data.data.items} initialProgress={data.data.progress} checks={data.data.checks} documentTypes={[]} active={active} />
    : <div>{data.error ? <p role="alert">{data.error}<button className="button-secondary" onClick={data.reload}>重新加载</button></p> : <p role="status">正在加载核验样本…</p>}</div>;
}

function Queue({ datasetId, kind, initial, initialProgress, documentTypes, checks, active }: {
  datasetId: string; kind: QueueKind; initial: QueueItem[]; initialProgress: GoldenProgress;
  documentTypes: GoldenSet["document_types"]; checks: AuditSet["checks"]; active: boolean;
}) {
  const token = useSessionToken();
  const storageKey = `golden-set-drafts:${datasetId}:${kind}`;
  const [items, setItems] = useState(initial);
  const [progress, setProgress] = useState(initialProgress);
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() => {
    try {
      const cached = JSON.parse(sessionStorage.getItem(storageKey) ?? "null");
      if (cached?.owner === token && cached.drafts) {
        const restored: Record<string, Draft> = {};
        for (const item of initial) {
          const draft = cached.drafts[itemId(item)];
          if (draft && typeof draft.primary === "string" && Array.isArray(draft.secondary) && typeof draft.note === "string" && Number.isSafeInteger(draft.revision) && draft.revision >= 0 && typeof draft.answers === "object" && draft.answers !== null) restored[itemId(item)] = { ...draft, dirty: true };
        }
        return restored;
      }
    } catch { /* A blocked browser store must not prevent server-backed work. */ }
    return {};
  });
  const [index, setIndex] = useState(() => {
    try { const cached = JSON.parse(sessionStorage.getItem(storageKey) ?? "null"); if (cached?.owner === token && Number.isInteger(cached.index) && cached.index >= 0 && cached.index < initial.length) return cached.index; } catch { /* Use the first unfinished server record. */ }
    const first = initial.findIndex(item => item.annotation?.status !== "annotated"); return first < 0 ? 0 : first;
  });
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [conflicts, setConflicts] = useState<Record<string, boolean>>({});
  const [latest, setLatest] = useState<{ id: string; annotation: SavedAnnotation | null } | null>(null);
  const [storageError, setStorageError] = useState(false);
  const item = items[index];
  const id = item ? itemId(item) : "";
  const source = item && "source_id" in item ? item : null;
  const draft = drafts[id] ?? makeDraft(item?.annotation ?? null);
  const types: TypeOption[] = documentTypes.map(option => typeof option === "string" ? { value: option, label: documentTypeLabels[option] ?? option } : option);
  const complete = kind === "sources" ? types.some(option => option.value === draft.primary) : checks.length > 0 && checks.every(check => Boolean(draft.answers[check.key]));
  const exposed = source ? source.prediction_exposed || Boolean(source.annotation?.prediction_exposed) : false;
  const conflict = Boolean(conflicts[id]);
  useEffect(() => {
    void Promise.resolve().then(() => sessionStorage.setItem(storageKey, JSON.stringify({ owner: token, drafts: Object.fromEntries(Object.entries(drafts).filter(([, value]) => value.dirty)), index }))).catch(() => setStorageError(true));
  }, [storageKey, token, drafts, index]);
  useEffect(() => {
    const dirty = Object.values(drafts).some(value => value.dirty);
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [drafts]);
  function edit(patch: Partial<Draft>) {
    if (lock.current || !item) return;
    setDrafts(previous => ({ ...previous, [id]: { ...(previous[id] ?? makeDraft(item.annotation)), ...patch, dirty: true } }));
    setMessage("");
  }
  function navigate(next: number) {
    if (lock.current || next < 0 || next >= items.length) return;
    setIndex(next); setRevealed(false); setError(""); setMessage(""); setLatest(null);
  }
  async function save(status: AnnotationStatus, advance: boolean) {
    if (lock.current || !item || conflict || (status === "annotated" && !complete)) return;
    lock.current = true; setBusy(true); setError(""); setMessage("");
    try {
      const result = kind === "sources" ? await saveGoldenAnnotation(id, {
        status, human_primary_type: draft.primary || null, human_secondary_types: draft.secondary.filter(value => value !== draft.primary),
        note: draft.note, expected_revision: draft.revision, prediction_exposed: exposed,
        ...(draft.informationalSafe ? { informational_safe: draft.informationalSafe } : {}),
      }) : await saveGoldenAudit(kind, id, { status, answers: draft.answers, note: draft.note, expected_revision: draft.revision });
      setItems(previous => previous.map(row => itemId(row) === id ? { ...row, annotation: result.annotation } as QueueItem : row));
      setProgress(result.progress);
      setDrafts(previous => ({ ...previous, [id]: makeDraft(result.annotation) }));
      setMessage(status === "draft" ? "草稿已保存到服务器。" : status === "skipped" ? "已跳过，未计入完成数。" : "人工标注已保存。");
      if (advance && index < items.length - 1) { setIndex(index + 1); setRevealed(false); setLatest(null); }
      else if (advance) setMessage("已保存，当前已是最后一条。可切换其他核验或查看评估。");
    } catch (failure) {
      setError(errorMessage(failure));
      if (failure instanceof ApiError && failure.status === 409) setConflicts(previous => ({ ...previous, [id]: true }));
    } finally { lock.current = false; setBusy(false); }
  }
  async function reveal() {
    if (lock.current || !source) return;
    lock.current = true; setBusy(true); setError("");
    try {
      const result = await exposeGoldenPrediction(id);
      if (!result.prediction_exposed) throw new Error("曝光记录尚未确认，请重试。");
      setItems(previous => previous.map(row => itemId(row) === id ? { ...row, prediction_exposed: true } : row));
      setRevealed(true);
    } catch (failure) { setError(errorMessage(failure)); }
    finally { lock.current = false; setBusy(false); }
  }
  async function fetchLatest() {
    if (lock.current) return;
    lock.current = true; setBusy(true);
    try {
      const refreshed = kind === "sources" ? await getGoldenSet() : await getGoldenAudits(kind);
      const remote = refreshed.items.find(row => itemId(row) === id);
      if (!remote) throw new Error("样本已不可用；本地填写仍保留。");
      setLatest({ id, annotation: remote.annotation }); setProgress(refreshed.progress);
      setItems(previous => previous.map(row => itemId(row) === id ? remote : row));
    } catch (failure) { setError(errorMessage(failure)); }
    finally { lock.current = false; setBusy(false); }
  }
  function resolveConflict(keepLocal: boolean) {
    if (!latest || latest.id !== id || lock.current) return;
    setDrafts(previous => ({ ...previous, [id]: keepLocal ? { ...draft, revision: latest.annotation?.revision ?? 0, dirty: true } : makeDraft(latest.annotation) }));
    setConflicts(previous => ({ ...previous, [id]: false })); setLatest(null); setError("");
    setMessage(keepLocal ? "当前填写已保留，请核对后再次保存。" : "已采用服务器版本。");
  }
  useEffect(() => {
    if (!active) return;
    function onKey(event: KeyboardEvent) {
      const target = event.target;
      if (event.isComposing || event.keyCode === 229 || event.repeat || event.defaultPrevented || (target instanceof HTMLElement && (target.closest("input:not([type='radio']):not([type='checkbox']),textarea,select,[contenteditable='true']") || target.isContentEditable))) return;
      if (event.altKey && !event.ctrlKey && !event.metaKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) { event.preventDefault(); navigate(index + (event.key === "ArrowLeft" ? -1 : 1)); return; }
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      if (kind === "sources" && shortcuts[event.key] && types.some(option => option.value === shortcuts[event.key])) { event.preventDefault(); edit({ primary: shortcuts[event.key], secondary: draft.secondary.filter(value => value !== shortcuts[event.key]), informationalSafe: "" }); }
      if (event.key === "Enter" && !(target instanceof HTMLElement && target.closest("button,a"))) { event.preventDefault(); void save("annotated", true); }
    }
    window.addEventListener("keydown", onKey); return () => window.removeEventListener("keydown", onKey);
  });
  return <section aria-label={`${labels[kind]}工作区`} className="space-y-4">
    <Progress value={progress} />
    {storageError ? <p role="alert" className="text-amber-800">浏览器无法保存本标签页草稿，请使用“保存草稿”后再刷新。</p> : null}
    {error ? <div role="alert" className="rounded-lg border border-red-200 bg-red-50 p-3 text-red-700"><p>{error}</p><p className="text-sm">当前填写仍保留；保存成功前不会进入下一条。</p></div> : null}
    {message ? <p role="status" className="text-sm text-emerald-800">{message}</p> : null}
    {!item ? <p className="panel p-6">暂无可标注样本。</p> : <>
      <div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm">第 {index + 1} / {items.length} 条 · #{id} · {item.annotation?.status === "annotated" ? "已完成人工标注" : item.annotation?.status === "draft" ? "服务端草稿" : item.annotation?.status === "skipped" ? "已跳过" : "未开始"} {draft.dirty ? <span className="text-amber-800">· 本标签页草稿（尚未提交服务器）</span> : null}</p><div className="flex gap-2"><button className="button-secondary" disabled={busy || index === 0} onClick={() => navigate(index - 1)}>上一条</button><button className="button-secondary" disabled={busy || index === items.length - 1} onClick={() => navigate(index + 1)}>下一条</button></div></div>
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(20rem,1fr)]">
        <article className="panel min-w-0 space-y-4 p-5">
          <h2 className="break-words text-xl font-semibold">{item.title}</h2>
          <dl className="grid grid-cols-2 gap-3 text-sm"><div><dt className="text-muted">学校</dt><dd>{item.school_name || "未提供"}</dd></div>{source ? <><div><dt className="text-muted">发布部门</dt><dd>{source.publisher || "未提供"}</dd></div><div><dt className="text-muted">发布日期</dt><dd>{source.published_at || "未提供"}</dd></div><div><dt className="text-muted">正文状态</dt><dd>{source.body_available ? "有已保存内容" : "正文缺失，请核对原文"}</dd></div></> : null}</dl>
          <div className="space-y-1">{sourceLink(item.source_url)}{item.source_url ? <p className="break-all text-xs text-muted">{item.source_url}</p> : null}</div>
          {!source && "audit_id" in item ? <div className="space-y-3 text-sm"><dl className="grid grid-cols-2 gap-3">{[["发布部门", item.publisher], ["发布日期", item.published_at], ["有效期开始", item.effective_from], ["有效期结束", item.effective_until]].map(([label, value]) => <div key={label}><dt className="text-muted">{label}</dt><dd>{value || "未提供"}</dd></div>)}</dl><div className="flex flex-wrap gap-3">{sourceLink(item.policy_url ?? null, "查看政策页面")}{sourceLink(item.attachment_url ?? null, "查看政策附件")}</div>{item.blocking_reasons?.length ? <p className="text-amber-800">待核验原因：{item.blocking_reasons.join("；")}</p> : null}</div> : null}
          <div className="max-h-[55vh] overflow-auto rounded-lg bg-surface p-4"><h3 className="mb-2 text-sm font-medium">已保存的原文内容</h3><p className="whitespace-pre-wrap break-words text-sm leading-7">{item.content_preview || "未保存正文内容，请打开来源核验；无法判断时可跳过。"}</p></div>
          {!source && "audit_id" in item ? <div className="space-y-3 text-sm">{item.competition_name || item.raw_competition_name ? <p>原文赛事：{item.raw_competition_name || "未提供"} · 匹配赛事：{item.competition_name || "未提供"} · 认可类型：{documentTypeLabels[item.recognition_type ?? ""] ?? item.recognition_type ?? "未提供"}</p> : null}{(item.entries ?? []).map((entry, position) => <details key={position} className="rounded-lg border border-line p-3" open><summary className="cursor-pointer font-medium">证据条目 {position + 1}</summary><dl className="mt-2 space-y-2">{Object.entries(entry).map(([key, value]) => <div key={key}><dt className="text-muted">{entryLabels[key] ?? key}</dt><dd className="whitespace-pre-wrap break-words">{display(value)}</dd></div>)}</dl></details>)}</div> : null}
        </article>
        <div className="panel min-w-0 space-y-4 p-5">
          {conflict ? <div className="space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm"><p>服务器版本已变化。先核对最新内容，再决定保留哪一份。</p><button className="button-secondary" disabled={busy} onClick={() => void fetchLatest()}>核对服务器最新版本</button>{latest?.id === id ? <><p>服务器版本 {latest.annotation?.revision ?? 0}</p><pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(latest.annotation, null, 2)}</pre><button className="button-secondary" disabled={busy} onClick={() => resolveConflict(true)}>保留当前填写，以最新版本继续</button><button className="button-secondary" disabled={busy} onClick={() => resolveConflict(false)}>采用服务器版本</button></> : null}</div> : null}
          <fieldset disabled={busy} className="space-y-4">
            {source ? <>
              <fieldset><legend className="mb-2 font-semibold">人工主类型（必选一项）</legend><div className="grid grid-cols-2 gap-2">{types.map(option => <label key={option.value} className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm ${draft.primary === option.value ? "border-accent bg-blue-50" : "border-line"}`}><input type="radio" name={`primary-${kind}`} value={option.value} checked={draft.primary === option.value} onChange={() => edit({ primary: option.value, secondary: draft.secondary.filter(value => value !== option.value), informationalSafe: "" })} />{option.label}</label>)}</div></fieldset>
              <details><summary className="cursor-pointer text-sm font-medium">次要类型（可选，已选 {draft.secondary.length} 项）</summary><div className="mt-2 grid grid-cols-2 gap-2">{types.map(option => <label key={option.value} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={draft.secondary.includes(option.value)} disabled={option.value === draft.primary} onChange={event => edit({ secondary: event.target.checked ? [...draft.secondary, option.value] : draft.secondary.filter(value => value !== option.value) })} />{option.label}</label>)}</div></details>
              {informationalTypes.has(draft.primary) ? <label className="grid gap-1 text-sm">可供信息参考且无重要变更？（可选）<select className="field" value={draft.informationalSafe} onChange={event => edit({ informationalSafe: event.target.value as Answer | "" })}><option value="">尚未核验</option>{Object.entries(answerLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span className="text-xs text-muted">请核对是否包含截止日期、规则或正式事实变化；主类型本身不能证明安全。</span></label> : null}
            </> : <div className="space-y-3"><h3 className="font-semibold">逐项核验</h3>{checks.map(check => <label key={check.key} className="grid gap-1 text-sm">{check.label}<select className="field" value={draft.answers[check.key] ?? ""} onChange={event => { const answers = { ...draft.answers }; if (event.target.value) answers[check.key] = event.target.value as Answer; else delete answers[check.key]; edit({ answers }); }}><option value="">请选择</option>{Object.entries(answerLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>)}</div>}
            <label className="grid gap-1 text-sm">标注备注<textarea className="field min-h-20 py-2" value={draft.note} onChange={event => edit({ note: event.target.value })} placeholder="判断依据、缺失材料或不确定之处（可选）" /></label>
          </fieldset>
          <div className="flex flex-wrap gap-2"><button className="button-primary disabled:opacity-50" disabled={busy || conflict || !complete} onClick={() => void save("annotated", true)}>保存并下一条</button><button className="button-secondary" disabled={busy || conflict} onClick={() => void save("draft", false)}>保存草稿</button><button className="button-secondary" disabled={busy || conflict} onClick={() => void save("skipped", true)}>跳过并下一条</button></div>
          <p className="text-xs leading-5 text-muted">{source ? "快捷键：1 报名 · 2 组织 · 3 选拔 · 4 结果 · 5 公示 · 6 完赛 · 7 介绍 · 8 认定政策 · 9 其他。" : "每个核验问题均需明确作答，不确定也可记录。"} Enter 保存并下一条；Alt + ← / → 翻页。输入文字时快捷键不触发。翻页仅保留本标签页草稿，点击“保存草稿”可跨设备恢复。</p>
          {source ? <div className="space-y-2 border-t border-line pt-4"><p className={`text-xs ${exposed ? "text-amber-800" : "text-muted"}`}>{exposed ? source.annotation?.status === "annotated" && !source.annotation.prediction_exposed ? "曾查看机器预测：已保存的标注保持盲标记录；再次保存会记录为看过预测。" : "曾查看机器预测：之后保存的标注不计入独立盲标。" : "机器预测默认隐藏，先完成人工判断可保持盲标。"}</p>{revealed ? <div className="space-y-2 rounded-lg bg-surface p-3 text-sm"><p>机器主类型：{documentTypeLabels[source.predicted_type] ?? source.predicted_type} · 置信度 {percent(source.predicted_confidence)}</p><p>机器次要类型：{source.predicted_secondary_types.map(value => documentTypeLabels[value] ?? value).join("、") || "无"}</p><p>{source.classification_reason || "未记录机器分类依据"}</p><p className="break-words text-xs text-muted">命中规则：{source.matched_rules.join("、") || "未提供"}</p><button className="button-secondary" onClick={() => setRevealed(false)}>收起机器预测</button></div> : <button className="button-secondary" disabled={busy} onClick={() => void reveal()}>查看机器预测</button>}</div> : null}
        </div>
      </div>
    </>}
  </section>;
}

function Metrics() {
  const metrics = usePrivateResource("golden-set-metrics", getGoldenMetrics);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const [error, setError] = useState("");
  async function download() {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError("");
    try {
      const data = await exportGoldenSet();
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const link = document.createElement("a"); link.href = url; link.download = `golden-set-${String(data.dataset_id ?? "export").replace(/[^a-zA-Z0-9_-]/g, "_")}.json`; link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (failure) { setError(errorMessage(failure)); }
    finally { lock.current = false; setBusy(false); }
  }
  const data: GoldenMetrics = metrics.data ?? {};
  const all = record(data.all_human); const blind = record(data.blind_human);
  const readiness = record(data.readiness ?? data.calibration_readiness);
  const blockers = readiness.blockers ?? readiness.reasons;
  const classes = record(data.per_class ?? all.per_class);
  const thresholds = Array.isArray(data.threshold_curves) ? data.threshold_curves as Array<Record<string, unknown>> : [];
  return <section aria-label="评估与导出" className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">人工标注评估</h2><div className="flex gap-2"><button className="button-secondary" onClick={metrics.reload}>刷新评估</button><button className="button-primary" disabled={busy} onClick={() => void download()}>导出标注与评估 JSON</button></div></div>
    {error || metrics.error ? <p role="alert" className="text-red-700">{error || metrics.error}</p> : null}
    {!metrics.ready ? <p role="status">正在计算人工样本评估…</p> : null}
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm"><p className="font-medium">{readiness.ready ? "样本核验已齐备；结果仍需人工评估。" : "校准未就绪：需完成 100 条分类、20 条政策和 20 条关系核验，并具备必要类别支持。"}</p><p className="mt-2">部分样本曲线仅供探索，不是已校准的生产设置。主类型标注不能证明不存在截止日期、规则或事实变化；未完成额外核验时不能据此宣称信息安全。此页不应用任何阈值。</p>{Array.isArray(blockers) ? <ul className="mt-2 list-inside list-disc">{blockers.map((value, i) => <li key={i}>{display(value)}</li>)}</ul> : null}</div>
    {metrics.data ? <>
      <div className="grid gap-4 sm:grid-cols-2">{[["全部人工标注", all, data.human_n], ["独立盲标", blind, data.blind_human_n]].map(([label, value, count]) => { const group = record(value); return <div key={String(label)} className="panel p-5"><h3 className="font-semibold">{String(label)}</h3><p className="mt-2 text-sm">有效样本 {display(group.human_n ?? group.count ?? count ?? 0)} · 准确率 {percent(group.accuracy)}</p></div>; })}</div>
      {Object.keys(classes).length ? <div className="panel overflow-x-auto p-4"><h3 className="mb-3 font-semibold">各类别表现</h3><table className="w-full text-left text-sm"><thead><tr>{["类型", "人工样本", "精确率", "召回率", "F1"].map(label => <th key={label} className="whitespace-nowrap p-2">{label}</th>)}</tr></thead><tbody>{Object.entries(classes).map(([type, value]) => { const row = record(value); return <tr key={type} className="border-t border-line"><th className="p-2 font-normal">{documentTypeLabels[type] ?? type}</th><td className="p-2">{display(row.support)}</td><td className="p-2">{percent(row.precision)}</td><td className="p-2">{percent(row.recall)}</td><td className="p-2">{percent(row.f1)}</td></tr>; })}</tbody></table></div> : null}
      {Object.keys(record(data.dangerous_errors)).length ? <div className="panel space-y-2 p-4"><h3 className="font-semibold">高风险误分</h3>{Object.entries(record(data.dangerous_errors)).map(([key, value]) => { const row = record(value); return <p key={key} className="text-sm">{dangerLabels[key] ?? display(row.definition ?? key)}：{display(row.count)} / {display(row.denominator)}（{percent(row.rate)}）</p>; })}</div> : null}
      {thresholds.length ? <div className="panel overflow-x-auto p-4"><h3 className="mb-3 font-semibold">探索性阈值曲线（未应用）</h3><table className="w-full text-left text-sm"><thead><tr>{["阈值", "已标注覆盖", "自动处理", "人工复核", "自动误判", "政策误判", "自动准确率"].map(label => <th key={label} className="whitespace-nowrap p-2">{label}</th>)}</tr></thead><tbody>{thresholds.map((row, i) => <tr key={i} className="border-t border-line">{[row.threshold, row.labeled_n, row.auto_n, row.review_n, row.wrong_auto_n, row.policy_wrong_auto_n, percent(row.auto_accuracy)].map((value, j) => <td key={j} className="p-2">{display(value)}</td>)}</tr>)}</tbody></table></div> : null}
      <details className="panel p-4"><summary className="cursor-pointer font-medium">完整评估数据（含混淆矩阵与核验统计）</summary><pre className="mt-3 max-h-[32rem] overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(metrics.data, null, 2)}</pre></details>
    </> : null}
  </section>;
}



