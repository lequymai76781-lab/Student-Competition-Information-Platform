"use client";

import Link from "next/link";
import { Flag } from "lucide-react";
import { useEffect, useState } from "react";

import { submitCorrection } from "@/lib/v09-api";

const types = [
  "报名截止错误",
  "官网失效",
  "学校通知遗漏",
  "学院通知遗漏",
  "赛事名称错误",
  "主办方错误",
  "其他",
];

export function CorrectionForm({ competitionId }: { competitionId: number }) {
  const [token, setToken] = useState<string | null>(null);
  const [correctionType, setCorrectionType] = useState(types[0]);
  const [description, setDescription] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sent, setSent] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setToken(window.localStorage.getItem("v09_token"));
    setReady(true);
  }, []);

  if (!ready) return null;
  if (!token) {
    return (
      <div className="panel-soft p-4 text-sm text-muted">
        发现信息有误？<Link href="/login" className="text-accent hover:underline">登录后</Link>可以提交纠错。
      </div>
    );
  }

  async function submit() {
    if (!description.trim()) return;
    await submitCorrection({
      competition_id: competitionId,
      correction_type: correctionType,
      description: description.trim(),
      source_url: sourceUrl.trim() || null,
    });
    setSent(true);
  }

  return (
    <div className="panel p-5">
      <div className="flex items-center gap-2">
        <Flag aria-hidden className="h-4 w-4 text-accent" />
        <p className="font-semibold text-ink">发现信息有误？</p>
      </div>
      <p className="mt-1 text-sm text-muted">提交后进入平台审核队列，不会直接修改数据库。可补充赛事信息或报告问题。</p>
      {sent ? (
        <p className="mt-3 text-sm text-emerald-700">已提交，审核人员会尽快处理。感谢反馈！</p>
      ) : (
        <div className="mt-4 grid gap-3">
          <select value={correctionType} onChange={(event) => setCorrectionType(event.target.value)} className="field">
            {types.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            placeholder="说明具体问题或补充的信息…"
            className="field min-h-20 py-2"
          />
          <input
            value={sourceUrl}
            onChange={(event) => setSourceUrl(event.target.value)}
            placeholder="来源URL（可选）"
            className="field"
          />
          <button type="button" disabled={!description.trim()} onClick={submit} className="button-secondary self-start">
            提交纠错
          </button>
        </div>
      )}
    </div>
  );
}
