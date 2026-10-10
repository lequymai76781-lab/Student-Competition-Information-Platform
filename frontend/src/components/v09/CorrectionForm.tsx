"use client";

import Link from "next/link";
import { Flag } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useReturnPath, useSessionToken } from "@/lib/use-session";

import { submitCorrection, submitSupplement } from "@/lib/v09-api";
import { SessionBoundary } from "@/components/v09/SessionBoundary";

const types = [
  "报名截止错误",
  "官网失效",
  "学校通知遗漏",
  "学院通知遗漏",
  "赛事名称错误",
  "主办方错误",
  "赛事历史补充", "其他",
];

const supplementTypes: Record<string, string> = { competition: "未收录赛事", school: "学校或专业", school_notice: "学校通知", recognition: "学校认定文件", history: "赛事历史资料", other: "其他遗漏" };

export function CorrectionForm({ competitionId, editionId }: { competitionId?: number; editionId?: number }) {
  return <SessionBoundary><CorrectionFormSession key={`${competitionId}-${editionId}`} competitionId={competitionId} editionId={editionId} /></SessionBoundary>;
}

function CorrectionFormSession({ competitionId, editionId }: { competitionId?: number; editionId?: number }) {
  const token = useSessionToken();
  const [correctionType, setCorrectionType] = useState(competitionId ? types[0] : "competition");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [sentId, setSentId] = useState<number | null>(null);
  const returnTo = useReturnPath();
  const [description, setDescription] = useState("");
  const [proposedValue, setProposedValue] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sent, setSent] = useState(false);
  if (!token) {
    return (
      <div className="panel-soft p-4 text-sm text-muted">
        学校、专业或赛事尚未收录，或发现信息有误？<Link href={`/login?next=${encodeURIComponent(returnTo)}`} className="text-accent hover:underline">登录后提交补充</Link>，由管理员核验整理。
      </div>
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || description.trim().length < 3) return;
    setBusy(true);
    setError("");
    try {
      const evidence = { description: description.trim(), source_url: sourceUrl.trim() || null };
      const value = proposedValue.trim();
      const proposed = value && correctionType === "报名截止错误" ? `${value}:00+08:00` : value;
      const result = competitionId ? await submitCorrection({ ...evidence, competition_id: competitionId,
        competition_edition_id: editionId, correction_type: correctionType, proposed_value: proposed || null })
        : await submitSupplement({ ...evidence, kind: correctionType, title: title.trim() });
      setSentId(result.id);
      setSent(true);
      window.dispatchEvent(new Event("v09-contribution-change"));
    } catch (exc) {
      setError(exc instanceof Error && exc.message !== "Failed to fetch" ? exc.message : "网络连接失败，内容已保留，请重试。");
    } finally { setBusy(false); }
  }

  return (
    <section className="panel p-5" aria-label="信息纠错与补充">
      <div className="flex items-center gap-2">
        <Flag aria-hidden className="h-4 w-4 text-accent" />
        <h2 className="font-semibold text-ink">{competitionId ? "纠错与补充" : "提交遗漏信息"}</h2>
      </div>
      <p className="mt-1 text-sm leading-6 text-muted">可补充学校通知、赛事官网、认定文件或历史资料。提交后进入待审核队列，核验完成前不会作为正式事实展示。</p>
      {sent ? (
        <div className="mt-3 text-sm" role="status"><p className="text-emerald-700">已提交，记录编号 {sentId}，当前状态：待审核。</p><Link href="/contribute?submitted=1" className="mt-3 inline-block text-accent">查看我的提交与审核意见</Link></div>
      ) : (
        <form onSubmit={submit} className="mt-4 grid gap-3">
          <label className="grid gap-2"><span className="label">信息类型</span><select value={correctionType} onChange={(event) => { setCorrectionType(event.target.value); setProposedValue(""); }} className="field">
            {(competitionId ? types : Object.keys(supplementTypes)).map((item) => (
              <option key={item} value={item}>
                {supplementTypes[item] ?? item}
              </option>
            ))}
          </select></label>
          {!competitionId ? <label className="grid gap-2"><span className="label">学校、专业或赛事名称</span><input required minLength={2} maxLength={200} value={title} onChange={(event) => setTitle(event.target.value)} className="field" placeholder="填写名称，方便核对" /></label> : null}
          {competitionId && correctionType === "报名截止错误" && editionId ? <label className="grid gap-2"><span className="label">建议报名截止时间（北京时间，可选）</span><input type="datetime-local" step="60" value={proposedValue} onChange={(event) => setProposedValue(event.target.value)} className="field" /><span className="text-xs text-muted">仅提交为候选值，由管理员核验本届来源后决定是否更新。</span></label> : null}
          {competitionId && ["赛事名称错误", "主办方错误", "官网失效"].includes(correctionType) ? <label className="grid gap-2"><span className="label">建议正确值（可选）</span><input type={correctionType === "官网失效" ? "url" : "text"} maxLength={500} value={proposedValue} onChange={(event) => setProposedValue(event.target.value)} className="field" /></label> : null}
          <label className="grid gap-2"><span className="label">具体说明</span><textarea
            required minLength={3} maxLength={4000}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            placeholder="说明具体问题或补充的信息…"
            className="field min-h-20 py-2"
          /></label>
          <label className="grid gap-2"><span className="label">来源网址（可选）</span><input
            type="url" pattern="https?://.*" maxLength={competitionId ? 1000 : 500}
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="来源URL（可选）"
            className="field"
          /></label>
          {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
          <button type="submit" disabled={busy || description.trim().length < 3 || (!competitionId && title.trim().length < 2)} className="button-primary justify-self-start">
            {busy ? "正在提交…" : competitionId ? "提交纠错" : "提交补充"}
          </button>
        </form>
      )}
    </section>
  );
}
