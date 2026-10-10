"use client";
import { useState } from "react";
import { reviewCandidateComplete, useReviewTiming } from "@/components/ReviewTelemetry";
import { approveFieldReviewBatch, previewFieldReviewBatch, type FieldReview, type FieldReviewConfig, type ReviewBatchPayload, type ReviewBatchPreview } from "@/lib/field-review-api";
import { reviewValue } from "@/components/FieldReviewDetail";

export function FieldReviewBatch({ selected, sourceTypes = [], onRemove, onClear, onCompleted, onSelect }: { selected: FieldReview[]; sourceTypes?: FieldReviewConfig["source_types"]; onRemove: (id: number) => void; onClear: () => void; onCompleted: (message: string) => void; onSelect: (id: number) => void }) {
  const timing = useReviewTiming();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [preview, setPreview] = useState<{ signature: string; data: ReviewBatchPreview; payload: ReviewBatchPayload } | null>(null);
  const payload: ReviewBatchPayload = { items: selected.map((row) => ({ id: row.id, preview_token: row.preview_token, field_names: row.low_risk_fields ?? row.bulk_eligible_fields })), note: note.trim() };
  const signature = JSON.stringify(payload);
  const active = preview?.signature === signature ? preview : null;
  const ready = Boolean(active && active.data.items.length === selected.length && active.data.items.every((row) => row.risk_level === "LOW_RISK" && (payload.items.find((item) => item.id === row.id)?.field_names ?? []).every((name) => row.bulk_eligible_fields.includes(name))));
  async function prepare() {
    setBusy(true); setError(""); setConfirmed(false); setPreview(null);
    try { const data = await previewFieldReviewBatch(payload); setPreview({ signature, data, payload }); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "批量预览失败，请重试。"); }
    finally { setBusy(false); }
  }
  async function submit() {
    if (!active || !ready || !confirmed || busy) return;
    setBusy(true); setError("");
    try { await timing.record(active.payload.items[0].id, "submit"); const result = await approveFieldReviewBatch(active.payload); timing.finish(result.items.filter(reviewCandidateComplete).map((item) => item.id)); onClear(); setPreview(null); setConfirmed(false); onCompleted(result.items.some((item) => !reviewCandidateComplete(item)) ? "整批 " + result.succeeded + " 条候选的选定字段已批准，其他字段仍待处理。" : "整批 " + result.succeeded + " 条候选已批准。"); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "整批提交失败，未批准任何候选。"); setPreview(null); setConfirmed(false); }
    finally { setBusy(false); }
  }
  const shown = active?.data.items ?? selected;
  const fields = selected.reduce((count, row) => count + (row.low_risk_fields ?? row.bulk_eligible_fields).length, 0);
  return <section aria-label="跨页批量审核" className="panel space-y-4 p-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">已选择 {selected.length} / 50 条候选</h2><button type="button" className="button-secondary text-sm" disabled={busy || !selected.length} onClick={onClear}>清空批量选择</button></div>
    <button type="button" className="button-secondary text-sm" disabled={busy || timing.busy || !selected.length} onClick={() => void timing.start(selected.map((row) => row.id))}>开始整批计时</button>
    <p className="text-sm text-muted">跨页保留选择 · {fields} 个字段 · 整批原子提交。高风险与学校关系材料需逐条审核；批准前须完成各来源核验。</p>
    {shown.length ? <div className="max-h-96 space-y-3 overflow-y-auto">{shown.map((row) => <div key={row.id} className="rounded-lg border border-line p-3 text-sm">
      <div className="flex flex-wrap items-center justify-between gap-2"><strong>{row.competition_name || "赛事 ID " + row.competition_id}</strong><span>学校：{row.collection_context?.school_name || (row.university_id ? "ID " + row.university_id : "无学校范围")}</span><button className="text-accent underline" type="button" onClick={() => onSelect(row.id)}>核对候选 #{row.id}</button><button type="button" className="text-muted underline" disabled={busy} onClick={() => onRemove(row.id)}>移除 #{row.id}</button></div>
      <p className="mt-1">{row.title} · {row.year ? row.year + " 年届次" : "赛事本体"}</p>
      {row.fields.filter((field) => (row.low_risk_fields ?? row.bulk_eligible_fields).includes(field.field_name)).map((field) => <div key={field.field_name} className="mt-2 border-t border-line pt-2">
        <p>{field.display_name}：{reviewValue(field.current_value)} → {reviewValue(field.candidate_value)}</p>
        <p>覆盖正式值：{field.current_value != null && field.change_type !== "unchanged" ? "是" : "否"} · 来源冲突：{field.risk_reasons?.includes("CONFLICT") ? "有" : "无"}</p>
        {field.proposals.map((proposal) => <p key={proposal.id} className="break-words text-xs text-muted">来源：{sourceTypes.find((type) => type.value === proposal.source?.source_type)?.label || proposal.source?.source_type || "未记录类型"} · {proposal.source?.source_title || "未记录标题"} · {proposal.source?.publisher || "未记录机构"} · {proposal.source?.verification_state === "VERIFIED" ? "已核验" : "待核验"}</p>)}
      </div>)}
    </div>)}</div> : <p className="text-sm text-muted">在队列中勾选低风险候选后查看整批摘要。</p>}
    <label className="grid gap-2 text-sm">批量审核意见<textarea className="field min-h-20 py-2" value={note} disabled={busy} onChange={(e) => setNote(e.target.value)} /></label>
    {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error} 选择、意见和筛选已保留，请重新核对后预览。</p> : null}
    <button type="button" className="button-secondary" disabled={busy || !selected.length || selected.length > 50 || !note.trim()} onClick={prepare}>预览批量批准</button>
    {active ? <div className="space-y-3 border-t border-line pt-4"><p className="text-sm">服务端预览：{active.data.total} 条候选、{active.data.field_count} 个字段；任何一条失败，整批不写入。</p>{!ready ? <p className="text-sm text-amber-800">部分来源尚未核验或已不符合低风险条件。请打开候选完成核验后重新预览。</p> : null}<label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={confirmed} disabled={busy || !ready} onChange={(e) => { setConfirmed(e.target.checked); if (e.target.checked && selected.length) void timing.record(selected[0].id, "decision", { decision: "approve" }); }} />已核对整批摘要，确认原子提交</label><button type="button" className="button-primary" disabled={busy || !confirmed || !ready} onClick={submit}>确认原子批准</button></div> : null}
  </section>;
}
