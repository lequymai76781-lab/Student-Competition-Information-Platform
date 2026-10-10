"use client";

import { useState } from "react";
import { useReviewLearning } from "@/components/ReviewLearning";
import { reviewDisplayRecord, reviewDisplayTitle } from "@/lib/review-learning-display";
import { createFieldReview, prepareFieldReview, type FieldReview, type FieldReviewConfig, type FieldReviewInput, type ReviewEntity, type ReviewValue } from "@/lib/field-review-api";

type DraftField = { field: string; value: string; clear: boolean; sourceType: string; title: string; url: string; publisher: string; published: string; confidence: string };
const emptyField = (): DraftField => ({ field: "", value: "", clear: false, sourceType: "", title: "", url: "", publisher: "", published: "", confidence: "" });

export function FieldReviewCandidateForm({ config, initial, onSaved, onCancel }: { config: FieldReviewConfig; initial?: FieldReview; onSaved: (row: FieldReview) => void; onCancel: () => void }) {
  const learning = useReviewLearning();
  const blindOriginal = Boolean(initial && learning.blind);
  const [entity, setEntity] = useState<ReviewEntity>(initial?.entity_type ?? "competition");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [competitionId, setCompetitionId] = useState(String(initial?.competition_id ?? ""));
  const [editionId, setEditionId] = useState(String(initial?.edition_id ?? ""));
  const [year, setYear] = useState(String(initial?.year ?? ""));
  const [schoolId, setSchoolId] = useState(String(initial?.university_id ?? ""));
  const [origin, setOrigin] = useState(initial?.origin ?? "manual_entry");
  const [fields, setFields] = useState<DraftField[]>([emptyField()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  function change(index: number, patch: Partial<DraftField>) { setFields((rows) => rows.map((row, i) => i === index ? { ...row, ...patch } : row)); }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError("");
    try {
      const payload: FieldReviewInput = {
        entity_type: entity, title: title.trim(), description: description.trim() || undefined,
        competition_id: competitionId ? Number(competitionId) : undefined,
        edition_id: entity === "edition" && editionId ? Number(editionId) : undefined,
        year: entity === "edition" && year ? Number(year) : undefined,
        university_id: schoolId ? Number(schoolId) : undefined, origin,
        fields: fields.map((row) => {
          const definition = config.fields[entity].find((item) => item.field_name === row.field);
          if (!definition) throw new Error("请选择每一行对应的字段。");
          let value: ReviewValue = row.clear ? null : row.value;
          if (!row.clear && /^(int|integer|float|number|boolean|bool|json|array|list|object)$/.test(definition.value_type)) {
            try { value = JSON.parse(row.value); } catch { throw new Error(`${definition.display_name}需要有效的 ${definition.value_type} 值。`); }
          }
          if (row.confidence && (!Number.isFinite(Number(row.confidence)) || Number(row.confidence) < 0 || Number(row.confidence) > 1)) throw new Error("置信度应在 0 到 1 之间。");
          const hasSource = Boolean(row.sourceType || row.title || row.url || row.publisher || row.published);
          return { field_name: row.field, candidate_value: value,
            confidence: row.confidence ? Number(row.confidence) : undefined,
            source: hasSource ? { source_type: row.sourceType || "manual_entry", source_title: row.title.trim() || undefined, source_url: row.url.trim() || undefined, publisher: row.publisher.trim() || undefined, published_at: row.published ? new Date(`${row.published}+08:00`).toISOString() : undefined } : undefined };
        }),
      };
      const row = initial ? await prepareFieldReview(initial.id, { ...payload, preview_token: initial.preview_token }) : await createFieldReview(payload);
      onSaved(row);
    } catch (exc) { setError(exc instanceof Error ? exc.message : "保存候选失败。"); }
    finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="panel p-5" aria-label={initial ? "整理自由文本候选" : "新建字段候选"}>
    <h2 className="text-lg font-semibold">{initial ? "将原始补充整理为字段候选" : "新建字段候选"}</h2>
    <p className="mt-2 text-sm text-muted">保存后进入审核队列。新赛事需批准赛事名称后才创建；新届次需明确所属赛事和年份，并至少批准一个字段。同一字段可添加多行，保留不同来源的候选值。</p>
    {error ? <p role="alert" className="mt-3 text-sm text-red-700">{error}</p> : null}
    <fieldset disabled={busy} className="mt-4 min-w-0 space-y-4">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">候选标题<input className="field" required readOnly={blindOriginal} value={blindOriginal && initial ? reviewDisplayTitle(initial, true) : title} onChange={(e) => setTitle(e.target.value)} /></label>
        <label className="grid gap-1 text-sm">目标实体类型<select className="field" value={entity} onChange={(e) => { setEntity(e.target.value as ReviewEntity); setFields([emptyField()]); }}><option value="competition">赛事本体</option><option value="edition">具体届次</option></select></label>
        <label className="grid gap-1 text-sm">目标赛事 ID<input className="field" type="number" min="1" step="1" required={entity === "edition"} placeholder={entity === "competition" ? "留空表示新赛事" : "所属赛事 ID"} value={competitionId} onChange={(e) => setCompetitionId(e.target.value)} /></label>
        {entity === "edition" ? <><label className="grid gap-1 text-sm">目标届次 ID<input className="field" type="number" min="1" step="1" placeholder="留空表示该年份的新届次" value={editionId} onChange={(e) => setEditionId(e.target.value)} /></label><label className="grid gap-1 text-sm">届次年份<input className="field" type="number" min="1900" max="2200" required value={year} onChange={(e) => setYear(e.target.value)} /></label></> : null}
        <label className="grid gap-1 text-sm">关联学校 ID（可选）<input className="field" type="number" min="1" step="1" value={schoolId} onChange={(e) => setSchoolId(e.target.value)} /></label>
        <label className="grid gap-1 text-sm">候选提交方式<select className="field" value={origin} disabled={Boolean(initial)} onChange={(e) => setOrigin(e.target.value)}><option value="manual_entry">人工整理</option><option value="user_submission">用户补充</option><option value="crawler">采集结果</option><option value="ai_assisted">AI 辅助提取</option></select></label>
      </div>
      <label className="grid gap-1 text-sm">原始说明<textarea aria-label="原始说明" className="field min-h-20 py-2" readOnly={blindOriginal} value={blindOriginal ? reviewDisplayRecord(description, true) : description} onChange={(e) => setDescription(e.target.value)} /></label>
      {fields.map((row, index) => <div key={index} className="panel-soft space-y-3 p-4">
        <div className="flex items-center justify-between gap-3"><h3 className="font-medium">候选行 {index + 1}</h3><button className="text-sm text-accent underline" type="button" onClick={() => setFields((rows) => rows.filter((_, i) => i !== index))}>移除此行</button></div>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="grid gap-1 text-sm">字段 {index + 1}<select className="field" required value={row.field} onChange={(e) => change(index, { field: e.target.value })}><option value="">选择字段</option>{config.fields[entity].map((item) => <option key={item.field_name} value={item.field_name}>{item.display_name}（{item.value_type}）</option>)}</select></label>
          <label className="grid gap-1 text-sm">候选值 {index + 1}<textarea className="field min-h-20 py-2" required={!row.clear} disabled={row.clear} placeholder="日期含时区；列表/数值/布尔值填写 JSON" value={row.value} onChange={(e) => change(index, { value: e.target.value })} /></label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={row.clear} onChange={(e) => change(index, { clear: e.target.checked })} />建议清空此字段（正式删除另需审核确认）</label>
          <label className="grid gap-1 text-sm">来源类型 {index + 1}<select className="field" value={row.sourceType} onChange={(e) => change(index, { sourceType: e.target.value })}><option value="">尚未提供来源</option>{config.source_types.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          <label className="grid gap-1 text-sm">来源标题 {index + 1}<input className="field" value={row.title} onChange={(e) => change(index, { title: e.target.value })} /></label>
          <label className="grid gap-1 text-sm">来源网址 {index + 1}<input className="field" type="url" value={row.url} onChange={(e) => change(index, { url: e.target.value })} /></label>
          <label className="grid gap-1 text-sm">发布机构 {index + 1}<input className="field" value={row.publisher} onChange={(e) => change(index, { publisher: e.target.value })} /></label>
          <label className="grid gap-1 text-sm">发布时间 {index + 1}（北京时间）<input className="field" type="datetime-local" value={row.published} onChange={(e) => change(index, { published: e.target.value })} /></label>
          <label className="grid gap-1 text-sm">置信度 {index + 1}（可选）<input className="field" type="number" min="0" max="1" step="0.01" value={row.confidence} onChange={(e) => change(index, { confidence: e.target.value })} /></label>
        </div>
      </div>)}
      {!fields.length ? <p className="text-sm text-amber-800">尚无字段：将保留为自由文本候选，正式批准前需要整理。</p> : null}
      <button type="button" className="button-secondary" onClick={() => setFields((rows) => [...rows, emptyField()])}>添加字段或替代来源</button>
      <div className="flex flex-wrap gap-3"><button className="button-primary" type="submit">{busy ? "正在保存…" : initial ? "保存结构化字段，等待审核" : "保存候选，等待审核"}</button><button className="button-secondary" type="button" onClick={onCancel}>取消</button></div>
    </fieldset>
  </form>;
}
