"use client";

import { useEffect, useState } from "react";

import { competitionContext, type V09Item } from "@/lib/v09-api";
import { formatDate } from "@/lib/format";

export function PersonalContext({ competitionId }: { competitionId: number }) {
  const [item, setItem] = useState<V09Item | null>(null);
  const [state, setState] = useState<"loading" | "guest" | "done" | "incomplete">("loading");

  useEffect(() => {
    const token = window.localStorage.getItem("v09_token");
    if (!token) {
      setState("guest");
      return;
    }
    competitionContext(competitionId)
      .then((result) => {
        if (result.found && result.item) {
          setItem(result.item);
          setState("done");
        } else {
          setState("incomplete");
        }
      })
      .catch(() => setState("guest"));
  }, [competitionId]);

  if (state === "guest" || state === "loading") return null;
  if (state === "incomplete" || !item) {
    return (
      <div className="panel-soft p-4">
        <p className="text-sm font-medium text-ink">与你相关</p>
        <p className="mt-1 text-xs text-muted">完善学校/专业后可查看本赛事与你的相关性。</p>
      </div>
    );
  }
  const deadlineInfo = item.effective_deadline
    ? `你的截止：${formatDate(item.effective_deadline)}（${item.effective_deadline_label ?? "报名截止"}）`
    : "暂未发现你的学校公开内部截止通知";
  return (
    <div className="panel-soft p-4">
      <p className="label">与你相关</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {item.reasons.slice(0, 6).map((reason) => (
          <span key={reason.type} className="tag-soft border-emerald-200 bg-emerald-50 text-emerald-700">
            ✓ {reason.text}
          </span>
        ))}
      </div>
      <p className="mt-2 text-sm text-muted">{deadlineInfo}</p>
      {item.college_deadline ? <p className="text-xs text-muted">学院截止：{formatDate(item.college_deadline)}</p> : null}
      {item.university_deadline ? <p className="text-xs text-muted">校内截止：{formatDate(item.university_deadline)}</p> : null}
    </div>
  );
}
