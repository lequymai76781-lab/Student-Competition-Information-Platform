"use client";
import { useState } from "react";
import { reviewDisplayRecord } from "@/lib/review-learning-display";
import { decideSchoolRelation, prepareSchoolRelation, verifySchoolRelation, type SchoolRelationPrepare, type SchoolRelationReview as Relation, type SchoolRelationPrepared } from "@/lib/field-review-api";
import { useReviewTiming } from "@/components/ReviewTelemetry";
import { useReviewLearning } from "@/components/ReviewLearning";
import { DocumentClassification } from "@/components/DocumentClassification";
import type { DocumentClassificationData } from "@/lib/document-policy-api";

const labels: Record<string, string> = { registration_notice: "报名通知", organization_notice: "组织参赛通知", selection_notice: "校内选拔", recommendation_notice: "推荐参赛", policy_recognition: "正式认定政策", award_policy: "奖励政策", repost: "转载信息", competition_notice: "赛事通知", other: "其他材料" };
const day = (value?: string | null) => value ? new Date(value).toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" }) : "";
const positive = (value: string) => /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value)) ? Number(value) : undefined;
export function SchoolRelationReview({ initial, classification, onQueueReload, onCompleted }: { initial: Relation; classification?: DocumentClassificationData | null; onQueueReload: () => void; onCompleted: (message: string) => void }) {
  const [relation, setRelation] = useState(initial);
  const [scope, setScope] = useState(initial.prepared.scope_type ?? "");
  const [students, setStudents] = useState(initial.prepared.student_scope ?? "");
  const [collegeId, setCollegeId] = useState(initial.prepared.college_id?.toString() ?? "");
  const [majorId, setMajorId] = useState(initial.prepared.major_id?.toString() ?? "");
  const [applicability, setApplicability] = useState(initial.prepared.applicability_text ?? "");
  const [validity, setValidity] = useState(initial.prepared.validity_note ?? "");
  const [evidence, setEvidence] = useState(initial.prepared.recognition_evidence ?? "");
  const [from, setFrom] = useState(day(initial.prepared.effective_from));
  const [until, setUntil] = useState(day(initial.prepared.effective_until));
  const [current, setCurrent] = useState(initial.prepared.current_validity_confirmed ?? false);
  const [schoolId, setSchoolId] = useState(initial.university_id?.toString() ?? "");
  const [competitionId, setCompetitionId] = useState(initial.competition_id?.toString() ?? "");
  const [identityEvidence, setIdentityEvidence] = useState("");
  const [year, setYear] = useState(initial.year?.toString() ?? "");
  const [editionId, setEditionId] = useState(initial.edition_id?.toString() ?? "");
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState<"" | "approve" | "reject" | "defer">("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const timing = useReviewTiming();
  const learning = useReviewLearning();
  const policy = relation.relation_kind === "policy";
  const completed = ["approved", "rejected"].includes(relation.status);
  const validDates = (!until || !from || until > from) && (!current || Boolean(from));
  const validIdentity = Boolean(positive(schoolId) && positive(competitionId) && ((initial.university_id && initial.competition_id) || identityEvidence.trim()));
  const readyPrepare = validIdentity && (policy ? Boolean(scope && students && applicability.trim() && validity.trim() && evidence.trim() && validDates && (scope !== "college" || positive(collegeId)) && (scope !== "major" || positive(majorId))) : Boolean(positive(year) || positive(editionId)));
  const saved = relation.prepared;
  const dirty = policy
    ? JSON.stringify([scope, students, scope === "college" ? collegeId : "", scope === "major" ? majorId : "", applicability.trim(), validity.trim(), evidence.trim(), from, until, current]) !== JSON.stringify([saved.scope_type ?? "", saved.student_scope ?? "", saved.scope_type === "college" ? String(saved.college_id ?? "") : "", saved.scope_type === "major" ? String(saved.major_id ?? "") : "", saved.applicability_text ?? "", saved.validity_note ?? "", saved.recognition_evidence ?? "", day(saved.effective_from), day(saved.effective_until), saved.current_validity_confirmed ?? false])
    : JSON.stringify([schoolId, competitionId, year, editionId]) !== JSON.stringify([String(relation.university_id ?? ""), String(relation.competition_id ?? ""), String(relation.year ?? ""), String(relation.edition_id ?? "")]);
  function preparePayload(): SchoolRelationPrepare {
    const payload: SchoolRelationPrepare = { preview_token: relation.preview_token, note: note.trim() };
    if (!relation.university_id) payload.university_id = positive(schoolId);
    if (!relation.competition_id) payload.competition_id = positive(competitionId);
    if (!relation.university_id || !relation.competition_id) payload.identity_evidence = identityEvidence.trim();
    if (policy) Object.assign(payload, {
      scope_type: scope as SchoolRelationPrepared["scope_type"], student_scope: students as SchoolRelationPrepared["student_scope"],
      applicability_text: applicability.trim(), validity_note: validity.trim(), recognition_evidence: evidence.trim(),
      current_validity_confirmed: current, effective_from: from ? from + "T00:00:00+08:00" : null,
      effective_until: until ? until + "T00:00:00+08:00" : null,
      ...(scope === "college" && positive(collegeId) ? { college_id: positive(collegeId) } : {}),
      ...(scope === "major" && positive(majorId) ? { major_id: positive(majorId) } : {}),
    });
    else { if (!relation.year && positive(year)) payload.year = positive(year); if (!relation.edition_id && positive(editionId)) payload.edition_id = positive(editionId); }
    return payload;
  }
  async function act(kind: "prepare" | "verify" | "review") {
    if (busy || !note.trim() || (kind === "review" && !decision)) return;
    setBusy(true); setError("");
    try {
      if (kind === "review") { await learning.beforeSubmit(relation.candidate_id); await timing.record(relation.candidate_id, "submit"); }
      const result = kind === "prepare" ? await prepareSchoolRelation(relation.candidate_id, preparePayload()) : kind === "verify" ? await verifySchoolRelation(relation.candidate_id, relation.preview_token, note.trim()) : await decideSchoolRelation(relation.candidate_id, relation.preview_token, note.trim(), decision as "approve" | "reject" | "defer", learning.enabled ? learning.entries[relation.candidate_id]?.session?.session_id : undefined);
      if (kind === "review") await learning.complete(relation.candidate_id);
      setRelation(result);
      if (kind === "prepare") { setSchoolId(String(result.university_id ?? schoolId)); setCompetitionId(String(result.competition_id ?? competitionId)); setYear(String(result.year ?? year)); setEditionId(String(result.edition_id ?? editionId)); }
      onQueueReload();
      if (kind === "review") {
        if (["approved", "rejected"].includes(result.status)) timing.finish([relation.candidate_id]);
        onCompleted(decision === "approve" ? "学校关系已批准。" : decision === "reject" ? "学校关系已拒绝，正式关系未改变。" : "学校关系已暂缓，仍待处理。");
      }
    } catch (exc) { if (kind === "review") learning.businessFailed(relation.candidate_id); setError(exc instanceof Error ? exc.message : "学校关系操作失败，请重试。"); }
    finally { setBusy(false); }
  }
  const safeUrl = relation.source?.source_url && /^https?:\/\//i.test(relation.source.source_url) ? relation.source.source_url : null;
  return <section aria-label="学校关系审核" className="panel space-y-4 p-5">
    <h3 className="font-semibold">学校关系审核{!learning.blind ? ` · ${labels[relation.notice_type] ?? relation.notice_type}` : ""}</h3>
    {!learning.blind && classification ? <DocumentClassification classification={classification} /> : null}
    <p className="text-sm">{relation.school_name || "学校待确认"} → {relation.competition_name || "赛事待确认"}{!learning.blind ? ` · ${policy ? "政策适用关系" : "具体届次通知"}` : ""}</p>
    <p className="text-xs text-muted">{learning.blind ? "学校关系与赛事字段分别审核。" : "材料类型固定；学校关系与赛事字段分别审核。普通通知不能转换成认定政策。"}</p>
    <div className="rounded-lg border border-line p-3 text-sm"><p>{relation.source?.source_title || "来源标题未记录"} · {relation.source?.publisher || "发布机构未记录"}</p><p>发布时间：{relation.source?.published_at || "未记录"} · 采集时间：{relation.source?.collected_at || "未记录"}</p><p>来源核验：{relation.source?.verification_state === "VERIFIED" ? "已人工核验" : "待人工核验"} · 可达性：{relation.source?.availability?.status || relation.source?.access_status || "UNKNOWN"}{relation.source?.source_failure_reason ? " · " + relation.source.source_failure_reason : ""}</p>{safeUrl ? <a className="mt-2 inline-block break-all text-accent underline" href={safeUrl} target="_blank" rel="noopener noreferrer" data-review-source="school" onClick={() => { void timing.record(relation.candidate_id, "source_open"); void learning.record(relation.candidate_id, "source_open"); }} onAuxClick={(event) => { if (event.button === 1) { void timing.record(relation.candidate_id, "source_open"); void learning.record(relation.candidate_id, "source_open"); } }}>打开学校来源原文</a> : null}</div>
    {relation.blocking_reasons.length ? <ul className="list-inside list-disc text-sm text-amber-800">{relation.blocking_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : null}
    {relation.flags.includes("RELATION_CONFLICT") ? <p className="text-sm text-red-700">学校关系存在冲突，需明确拒绝或暂缓，不能直接批准覆盖。</p> : null}
    <fieldset disabled={busy || completed} className="space-y-4">
      {(!initial.university_id || !initial.competition_id) ? <div className="grid gap-3 sm:grid-cols-2">
        {!initial.university_id ? <label className="grid gap-1 text-sm">学校身份 ID<input className="field" type="number" min="1" value={schoolId} onChange={(e) => setSchoolId(e.target.value)} /></label> : null}
        {!initial.competition_id ? <label className="grid gap-1 text-sm">赛事身份 ID<input className="field" type="number" min="1" value={competitionId} onChange={(e) => setCompetitionId(e.target.value)} /></label> : null}
        <label className="grid gap-1 text-sm sm:col-span-2">身份确认依据<textarea className="field min-h-20 py-2" value={identityEvidence} onChange={(e) => setIdentityEvidence(e.target.value)} /></label>
      </div> : null}
      {policy ? <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">政策范围<select className="field" value={scope} onChange={(e) => setScope(e.target.value as typeof scope)}><option value="">明确选择范围</option><option value="university">学校</option><option value="college">学院</option><option value="major">专业</option></select></label>
        <label className="grid gap-1 text-sm">适用学生<select className="field" value={students} onChange={(e) => setStudents(e.target.value as typeof students)}><option value="">明确选择学生范围</option><option value="undergraduate">本科生</option><option value="graduate">研究生</option><option value="all">全部学生</option><option value="other">其他特定学生</option></select></label>
        {scope === "college" ? <label className="grid gap-1 text-sm">学院 ID<input className="field" type="number" min="1" value={collegeId} onChange={(e) => setCollegeId(e.target.value)} /></label> : null}
        {scope === "major" ? <label className="grid gap-1 text-sm">专业 ID<input className="field" type="number" min="1" value={majorId} onChange={(e) => setMajorId(e.target.value)} /></label> : null}
        <label className="grid gap-1 text-sm sm:col-span-2">适用范围说明<textarea className="field min-h-20 py-2" value={applicability} onChange={(e) => setApplicability(e.target.value)} /></label>
        <label className="grid gap-1 text-sm">有效期开始<input className="field" type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
        <label className="grid gap-1 text-sm">有效期结束<input className="field" type="date" value={until} onChange={(e) => setUntil(e.target.value)} /></label>
        <label className="grid gap-1 text-sm sm:col-span-2">有效期说明<textarea className="field min-h-20 py-2" value={validity} onChange={(e) => setValidity(e.target.value)} /></label>
        <label className="grid gap-1 text-sm sm:col-span-2">赛事认定条款<textarea className="field min-h-20 py-2" value={evidence} onChange={(e) => setEvidence(e.target.value)} /></label>
        <label className="flex items-center gap-2 text-sm sm:col-span-2"><input type="checkbox" checked={current} onChange={(e) => setCurrent(e.target.checked)} />确认当前仍然有效</label>
        <p className="text-xs text-muted sm:col-span-2">{current ? "须有明确起始日期且当前处于有效期内，仍由服务器检查。" : "当前效力未确认，仅保存历史适用表达。"} 修改准备信息后须重新核验来源。</p>
      </div> : <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm">通知届次年份<input className="field" type="number" min="1900" max="2200" value={year} disabled={Boolean(relation.year)} onChange={(e) => setYear(e.target.value)} /></label>
        <label className="grid gap-1 text-sm">通知届次 ID<input className="field" type="number" min="1" value={editionId} disabled={Boolean(relation.edition_id)} onChange={(e) => setEditionId(e.target.value)} /></label>
        <p className="text-xs text-muted sm:col-span-2">只可补明确的未知届次，已知年份和学校/赛事身份不能替换。</p>
      </div>}
      <label className="grid gap-2 text-sm">关系审核意见<textarea className="field min-h-20 py-2" value={note} onChange={(e) => setNote(e.target.value)} /></label>
      <div className="flex flex-wrap gap-3"><button type="button" className="button-secondary" disabled={!note.trim() || !readyPrepare} onClick={() => void act("prepare")}>保存关系准备</button><button type="button" className="button-secondary" disabled={dirty || !note.trim() || !relation.source || relation.source.verification_state === "VERIFIED"} onClick={() => void act("verify")}>已核对学校原始来源</button></div>
      {dirty ? <p className="text-sm text-amber-800">准备信息有未保存的修改，请先保存，再重新核验来源。</p> : null}
      <label className="grid gap-2 text-sm">关系处理方式<select className="field" value={decision} onChange={(e) => { const value = e.target.value as typeof decision; setDecision(value); if (value) { void timing.record(relation.candidate_id, "decision", { decision: value }); void learning.record(relation.candidate_id, "decision", { decision: value }); } }}><option value="">明确选择处理方式</option><option value="approve">批准此学校关系</option><option value="reject">拒绝材料</option><option value="defer">暂缓处理</option></select></label>
      <button className="button-primary" type="button" disabled={!note.trim() || !decision || !learning.canSubmit(relation.candidate_id) || (decision === "approve" && (dirty || !relation.can_approve || relation.flags.includes("RELATION_CONFLICT")))} onClick={() => void act("review")}>提交学校关系审核</button>
    </fieldset>
    {completed ? <p role="status" className="text-sm">学校关系已{relation.status === "approved" ? "批准" : "拒绝"}，操作已留存审计记录。</p> : null}
    {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p> : null}
    {relation.existing_records.length ? <details><summary className="cursor-pointer text-sm text-accent">已有关系与合并范围（{relation.existing_records.length} 条）</summary><pre className="mt-2 whitespace-pre-wrap break-words text-xs">{reviewDisplayRecord(relation.existing_records, learning.blind)}</pre></details> : null}
    {relation.history?.length ? <details><summary className="cursor-pointer text-sm text-accent">关系审核历史</summary><pre className="mt-2 whitespace-pre-wrap break-words text-xs">{reviewDisplayRecord(relation.history, learning.blind)}</pre></details> : null}
  </section>;
}
