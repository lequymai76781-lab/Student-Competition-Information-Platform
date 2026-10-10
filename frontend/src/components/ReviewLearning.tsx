"use client";
import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { primaryDocumentTypes, type PrimaryDocumentType } from "@/lib/document-policy-api";
import { completeLearningSession, learningConfig, learningEvent, startLearningSession, type LearningConfig, type LearningEvent, type LearningExample, type LearningLabels, type LearningSession } from "@/lib/review-learning-api";
import { usePrivateResource } from "@/lib/use-private-resource";
import { useSessionToken } from "@/lib/use-session";

type Entry = { session?: LearningSession; primary: string; secondary: string; risk: string; phase: "starting" | "ready" | "submitting" | "pending" | "saving" | "saved" | "error"; error: string; example?: LearningExample };
type LearningContext = { enabled: boolean; blind: boolean; config: LearningConfig | null; configError: string; reloadConfig: () => void; entries: Record<number, Entry>; start: (id: number, fresh?: boolean) => Promise<void>; setLabels: (id: number, patch: Partial<Pick<Entry, "primary" | "secondary" | "risk">>) => void; record: (id: number, event: LearningEvent, details?: Record<string, unknown>) => Promise<void>; canSubmit: (id: number) => boolean; beforeSubmit: (id: number) => Promise<void>; businessFailed: (id: number) => void; complete: (id: number) => Promise<void> };
const noop = async () => {};
const Context = createContext<LearningContext>({ enabled: false, blind: false, config: null, configError: "", reloadConfig: () => {}, entries: {}, start: noop, setLabels: () => {}, record: noop, canSubmit: () => true, beforeSubmit: noop, businessFailed: () => {}, complete: noop });
export const useReviewLearning = () => useContext(Context);
const message = (error: unknown) => error instanceof Error ? error.message : "学习记录暂不可用，请重试。";
const labels = (entry: Entry): LearningLabels => ({ human_primary_type: entry.primary as PrimaryDocumentType, ...(entry.secondary.trim() ? { human_secondary_type: entry.secondary.trim() } : {}), ...(entry.risk ? { human_risk_level: entry.risk } : {}) });

export function ReviewLearningProvider({ children }: { children: ReactNode }) {
  const token = useSessionToken();
  const config = usePrivateResource("review-learning-config", learningConfig);
  const enabled = config.data?.enabled === true;
  // Unknown/error config must not expose model hints while a blind review may be active.
  const blind = !config.ready || Boolean(config.error) || enabled;
  const [entries, setEntries] = useState<Record<number, Entry>>({});
  const state = useRef<Record<number, Entry>>({});
  const serial = useRef<Record<number, Promise<void>>>({});
  const owned = useCallback(() => Boolean(token) && window.localStorage.getItem("v09_token") === token, [token]);
  const patch = useCallback((id: number, update: Partial<Entry>) => {
    if (!owned()) return;
    state.current = { ...state.current, [id]: { ...state.current[id], ...update } };
    setEntries(state.current);
  }, [owned]);
  const start = useCallback(async (id: number, fresh = false) => {
    if (!enabled || !owned() || (!fresh && state.current[id]) || state.current[id]?.phase === "starting") return;
    patch(id, { primary: "", secondary: "", risk: "", phase: "starting", error: "", session: undefined, example: undefined });
    try {
      const result = await startLearningSession(id);
      if (!owned()) return;
      if (result.candidate_id !== id || !(result.session_id || result.id)) throw new Error("学习会话与当前候选不符，请重试。");
      patch(id, { session: { ...result, session_id: result.session_id || result.id! }, phase: "ready" });
    } catch (error) { patch(id, { phase: "error", error: message(error) }); }
  }, [enabled, owned, patch]);
  function record(id: number, event: LearningEvent, details?: Record<string, unknown>) {
    const entry = state.current[id];
    if (!enabled || !entry?.session || !["ready", "submitting"].includes(entry.phase) || !owned()) return Promise.resolve();
    const sessionId = entry.session.session_id;
    const operation = (serial.current[id] ?? Promise.resolve()).catch(() => {}).then(async () => {
      if (!owned()) throw new Error("登录状态已变化，请重新打开审核。");
      await learningEvent(sessionId, event, details);
    });
    serial.current[id] = operation;
    return operation.catch((error: unknown) => { patch(id, { error: message(error) }); if (event === "submit") throw error; });
  }
  function setLabels(id: number, update: Partial<Pick<Entry, "primary" | "secondary" | "risk">>) {
    if (state.current[id]?.phase !== "ready") return;
    patch(id, update); void record(id, "decision", { dimension: "classification" });
  }
  function canSubmit(id: number) {
    if (!config.ready || config.error) return false;
    return !enabled || Boolean(state.current[id]?.phase === "ready" && state.current[id]?.primary);
  }
  async function beforeSubmit(id: number) {
    if (!canSubmit(id)) throw new Error("请先完成学习会话并明确选择人工一级类型。");
    if (!enabled) return;
    const entry = state.current[id];
    patch(id, { phase: "submitting", error: "" });
    try { await record(id, "submit", labels(entry)); }
    catch (error) { patch(id, { phase: "ready" }); throw error; }
  }
  function businessFailed(id: number) { if (state.current[id]?.phase === "submitting") patch(id, { phase: "ready" }); }
  async function complete(id: number) {
    const entry = state.current[id];
    if (!enabled || !entry?.session || entry.phase === "saving" || entry.phase === "saved" || !owned()) return;
    patch(id, { phase: "saving", error: "" });
    try {
      const example = await completeLearningSession(entry.session.session_id, labels(entry));
      patch(id, { phase: "saved", example });
    } catch (error) { patch(id, { phase: "pending", error: "业务审核已保存，学习样本尚未保存：" + message(error) }); }
  }
  return <Context.Provider value={{ enabled, blind, config: config.data, configError: config.error, reloadConfig: config.reload, entries, start, setLabels, record, canSubmit, beforeSubmit, businessFailed, complete }}>{children}</Context.Provider>;
}

export function ReviewLearningControls({ candidateId, completed = false }: { candidateId: number; completed?: boolean }) {
  const learning = useReviewLearning();
  const { start } = learning;
  useEffect(() => { if (!completed) void start(candidateId); }, [candidateId, completed, start]);
  if (learning.configError) return <div role="alert" className="panel p-4 text-sm text-red-700">学习配置加载失败：{learning.configError}<button className="ml-3 underline" onClick={learning.reloadConfig}>重新加载学习配置</button></div>;
  if (!learning.enabled) return null;
  const entry = learning.entries[candidateId];
  if (!entry && completed) return null;
  const editable = entry?.phase === "ready";
  return <section aria-label="人工独立判断" className="panel space-y-3 p-5">
    <div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold">人工独立判断</h3><Link className="text-sm text-accent underline" href="/admin/review-learning">查看学习状态</Link></div>
    <p className="text-sm text-muted">请阅读来源后独立选择类型，再提交原有审核。每次审核独立记录；系统预测在提交前隐藏。</p>
    {learning.config?.actor_mode === "automation" ? <p className="text-sm text-amber-800">当前为自动化环境，不计入真实人工样本。</p> : null}
    <label className="grid gap-1 text-sm">人工一级类型<select aria-label="人工一级类型" className="field" required disabled={!editable} value={entry?.primary ?? ""} onChange={(event) => learning.setLabels(candidateId, { primary: event.target.value })}><option value="">请选择</option>{primaryDocumentTypes.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
    <details><summary className="cursor-pointer text-sm text-accent">补充二级类型或风险（可选）</summary><div className="mt-3 grid gap-3 sm:grid-cols-2"><label className="grid gap-1 text-sm">人工二级类型<input className="field" disabled={!editable} value={entry?.secondary ?? ""} onChange={(event) => learning.setLabels(candidateId, { secondary: event.target.value })} placeholder="未填写则保持缺失" /></label><label className="grid gap-1 text-sm">人工风险判断<select className="field" disabled={!editable} value={entry?.risk ?? ""} onChange={(event) => learning.setLabels(candidateId, { risk: event.target.value })}><option value="">暂不判断</option><option value="LOW_RISK">低风险</option><option value="NORMAL">普通风险</option><option value="HIGH_RISK">高风险</option></select></label></div></details>
    {(!entry || entry.phase === "starting") ? <p role="status" className="text-sm">正在建立独立审核会话…</p> : null}
    {entry?.phase === "submitting" || entry?.phase === "saving" ? <p role="status" className="text-sm">正在保存审核记录…</p> : null}
    {entry?.error ? <p role="alert" className="text-sm text-red-700">{entry.error}</p> : null}
    {entry?.phase === "error" ? <button className="button-secondary" onClick={() => void start(candidateId, true)}>重试建立学习会话</button> : null}
    {entry?.phase === "pending" ? <button className="button-secondary" onClick={() => void learning.complete(candidateId)}>仅重试保存学习样本</button> : null}
    {entry?.phase === "saved" ? <><p role="status" className="text-sm text-emerald-800">学习样本已保存，当前人工判断已锁定。</p>{!completed ? <button className="button-secondary" onClick={() => void start(candidateId, true)}>开始下一次独立审核</button> : null}</> : null}
  </section>;
}
