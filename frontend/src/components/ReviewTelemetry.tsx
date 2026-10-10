"use client";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { fieldReviewStatistics, sendReviewTimingEvent, startReviewTiming, type FieldReview, type ReviewMode, type ReviewTimingEvent, type ReviewTimingSession, type ReviewTimingSummary } from "@/lib/field-review-api";
import { ApiError } from "@/lib/v09-api";
import { usePrivateResource } from "@/lib/use-private-resource";

type EventExtra = { proposal_id?: string; field_name?: string; decision?: "approve" | "reject" | "defer" };
type TimingContext = { mode: ReviewMode; setMode: (mode: ReviewMode) => void; session: ReviewTimingSession | null; busy: boolean; error: string; start: (ids: number[]) => Promise<void>; record: (id: number, event: ReviewTimingEvent, extra?: EventExtra) => Promise<void>; finish: (ids: number[]) => void };
const noop = async () => {};
const Context = createContext<TimingContext>({ mode: "human", setMode: () => {}, session: null, busy: false, error: "", start: noop, record: noop, finish: () => {} });
export const useReviewTiming = () => useContext(Context);
export function reviewCandidateComplete(row: Pick<FieldReview, "status" | "fields">) {
  return row.fields.length > 0 ? row.fields.every((field) => ["approved", "rejected"].includes(field.decision)) : ["approved", "rejected"].includes(row.status);
}
export function ReviewTimingProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ReviewMode>("human");
  const [session, setSession] = useState<ReviewTimingSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const membersDone = useRef(new Set<number>());
  const serial = useRef<Promise<void>>(Promise.resolve());
  async function start(ids: number[]) {
    if (!ids.length || busy) return;
    setBusy(true); setError("");
    try {
      await serial.current;
      const result = await startReviewTiming(ids[0], mode, ids.length > 1 ? ids : undefined);
      membersDone.current = new Set();
      setSession(result);
    } catch (exc) { setError(exc instanceof Error ? exc.message : "计时未能开始。"); }
    finally { setBusy(false); }
  }
  function record(id: number, event: ReviewTimingEvent, extra: EventExtra = {}) {
    if (!session || session.status !== "active" || !(session.candidate_ids ?? [session.candidate_id]).includes(id)) return Promise.resolve();
    const saved = session;
    serial.current = serial.current.then(async () => {
      try {
        const result = await sendReviewTimingEvent(saved.candidate_id, { session_id: saved.session_id, event, ...extra });
        setSession((current) => current?.session_id === saved.session_id ? { ...current, ...result } : current);
      } catch (exc) {
        if (exc instanceof ApiError && exc.status === 409) setSession((current) => current?.session_id === saved.session_id ? { ...current, status: "invalid" } : current);
        setError((exc instanceof Error ? exc.message : "计时打点未保存，本次时长可能不完整。") + (exc instanceof ApiError && exc.status === 409 ? " 请明确重新开始计时；此前记录不自动算作完成。" : ""));
      }
    });
    return serial.current;
  }
  function finish(ids: number[]) {
    for (const id of ids) membersDone.current.add(id);
    setSession((current) => current && current.status === "active" && (current.candidate_ids ?? [current.candidate_id]).every((id) => membersDone.current.has(id)) ? { ...current, status: "completed" } : current);
  }
  return <Context.Provider value={{ mode, setMode, session, busy, error, start, record, finish }}>{children}</Context.Provider>;
}
export function ReviewTimingControls() {
  const timing = useReviewTiming();
  return <section aria-label="审核计时" className="panel space-y-3 p-4">
    <div className="flex flex-wrap items-center gap-4"><h2 className="font-semibold">审核计时</h2><label className="flex items-center gap-2 text-sm">计时模式<select className="field" value={timing.mode} disabled={timing.busy || timing.session?.status === "active"} onChange={(e) => timing.setMode(e.target.value as ReviewMode)}><option value="human">人工实测</option><option value="automation">自动化实验</option></select></label></div>
    <p className="text-xs text-muted">明确开始后，以服务端时间记录打开来源、选择决定和提交。阶段打点不等同实际阅读时长；暂缓和部分处理保留为未完成样本。自动化时长单独统计。</p>
    {timing.session ? <p role="status" className="text-sm">{timing.session.status === "active" ? (timing.session.mode === "human" ? "人工计时进行中" : "自动化计时进行中") : timing.session.status === "completed" ? "本次计时已完成" : "本次计时已失效，请重新开始"}{timing.session.sample_type === "batch" ? " · 整批共用一份墙钟时间" : null}</p> : null}
    {timing.error ? <p role="alert" className="text-sm text-amber-800">{timing.error}</p> : null}
  </section>;
}
export function StartReviewTiming({ candidateId }: { candidateId: number }) {
  const timing = useReviewTiming();
  const active = timing.session?.status === "active" && (timing.session.candidate_ids ?? [timing.session.candidate_id]).includes(candidateId);
  return <button type="button" className="button-secondary text-sm" disabled={timing.busy || active} onClick={() => void timing.start([candidateId])}>{active ? "本条已纳入计时" : "开始本条计时"}</button>;
}
const countLabels: Record<string, string> = { pending: "待审核", approved: "已批准", rejected: "已拒绝", partially_approved: "部分批准", deferred: "暂缓处理", conflict: "来源冲突", no_source: "缺少来源", duplicate_suspected: "疑似重复", low_risk: "低风险", high_risk: "高风险", school_relations: "学校关系" };
function metric(value?: number | null, suffix = "秒") { return value == null || !Number.isFinite(value) ? "暂无完成样本" : value.toFixed(1) + suffix; }
function TimingSummary({ title, group }: { title: string; group?: ReviewTimingSummary }) {
  return <div className="rounded-lg border border-line p-3 text-sm"><h3 className="font-medium">{title}</h3><p className="mt-2">完成样本 {group?.completed_samples ?? 0} · 处理候选 {group?.completed_candidates ?? 0}</p><p>进行中 {group?.active_sessions ?? 0} · 中断 {group?.interrupted_sessions ?? 0}</p><p className="mt-2">均值 {metric(group?.mean_seconds)} · 中位数 {metric(group?.median_seconds)} · P90 {metric(group?.p90_seconds)}</p><p>理论每小时量：{metric(group?.theoretical_per_hour, "条/小时")}</p>{group?.by_sample_type ? <p className="mt-2 text-xs text-muted">单条完成 {group.by_sample_type.single?.completed_samples ?? 0} · 批量完成 {group.by_sample_type.batch?.completed_samples ?? 0}（按真实墙钟时间）</p> : null}</div>;
}
export function ReviewStatisticsPanel({ revision }: { revision: number }) {
  const load = useCallback(() => fieldReviewStatistics(), []);
  const stats = usePrivateResource("review-statistics-" + revision, load);
  return <section aria-label="审核统计" className="panel space-y-3 p-4"><div className="flex items-center justify-between gap-3"><h2 className="font-semibold">审核统计</h2><button className="text-sm text-accent underline" type="button" onClick={stats.reload}>刷新统计</button></div>{stats.error ? <p role="alert" className="text-sm text-red-700">{stats.error}</p> : null}
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-5">{Object.entries(countLabels).map(([key, label]) => <div className="rounded-lg bg-slate-50 p-2" key={key}><dt className="text-xs text-muted">{label}</dt><dd className="mt-1 font-semibold">{stats.data?.counts?.[key] ?? "—"}</dd></div>)}</dl>
    <div className="grid gap-3 lg:grid-cols-2"><TimingSummary title="人工实测" group={stats.data?.telemetry?.groups?.human} /><TimingSummary title="自动化实验" group={stats.data?.telemetry?.groups?.automation} /></div>
    <p className="text-xs text-muted">本审核人已处理候选 {stats.data?.telemetry?.processed_candidates ?? "—"} 条 · 未知或未完成时长 {stats.data?.telemetry?.unknown_duration_candidates ?? "—"} 条。</p>
    <p className="text-xs text-muted">理论产能基于已完成样本，未完成和未知时长不混入均值；这不是持续人工工作效率的承诺。</p>
  </section>;
}
