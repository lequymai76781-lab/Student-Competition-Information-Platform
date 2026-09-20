"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { setFavorite, setStatus, type V09Item } from "@/lib/v09-api";
import { formatDate } from "@/lib/format";

const statusOptions = ["interested", "planning", "registered", "participating", "finished", "abandoned"];
const statusLabels: Record<string, string> = {
  interested: "感兴趣",
  planning: "准备参加",
  registered: "已报名",
  participating: "进行中",
  finished: "已完成",
  abandoned: "放弃",
};

export function PersonalItemCard({ item, onChanged }: { item: V09Item; onChanged?: () => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [favorite, setFavoriteState] = useState(item.favorite ?? false);
  const [status, setStatusState] = useState(item.user_status ?? "");

  async function toggleFavorite() {
    setBusy(true);
    try {
      await setFavorite(item.competition_id, !favorite);
      setFavoriteState((value) => !value);
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(value: string) {
    setBusy(true);
    try {
      await setStatus(item.competition_id, value);
      setStatusState(value);
      onChanged?.();
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="panel-interactive p-5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <Link href={`/competitions/${item.competition_id}`} className="min-w-0">
          <h3 className="font-semibold text-ink hover:text-accent">{item.name}</h3>
          <p className="mt-1 text-xs text-muted">
            {item.category ?? "方向暂未核实"} · {item.current_status ?? "届次状态暂未核实"}
          </p>
        </Link>
        <span className="badge">{statusLabels[status] ?? (status ? status : "未设置状态")}</span>
      </div>

      {item.effective_deadline ? (
        <div className="mt-3 rounded-md border border-orange-100 bg-orange-50 px-3 py-2 text-sm">
          <span className="font-semibold text-orange-700">你的截止：{formatDate(item.effective_deadline)}</span>
          <span className="ml-2 text-xs text-orange-600">{item.effective_deadline_label}</span>
          {item.college_deadline ? <p className="mt-0.5 text-xs text-muted">学院截止：{formatDate(item.college_deadline)}</p> : null}
          {item.university_deadline ? <p className="text-xs text-muted">校内截止：{formatDate(item.university_deadline)}</p> : null}
          {item.official_deadline && !item.college_deadline && !item.university_deadline ? (
            <p className="text-xs text-muted">官方截止：{formatDate(item.official_deadline)}</p>
          ) : null}
        </div>
      ) : (
        <p className="mt-3 text-xs text-muted">截止时间暂未核实</p>
      )}

      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.reasons.slice(0, 4).map((reason) => (
          <span key={reason.type} className="tag-soft border-emerald-200 bg-emerald-50 text-emerald-700">
            ✓ {reason.text}
          </span>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-line pt-3">
        <Link href={`/competitions/${item.competition_id}`} className="button-secondary px-3 text-sm">
          查看详情
        </Link>
        <button type="button" disabled={busy} onClick={toggleFavorite} className="button-secondary px-3 text-sm">
          {favorite ? "已收藏" : "收藏"}
        </button>
        <select
          value={status}
          disabled={busy}
          onChange={(event) => changeStatus(event.target.value)}
          className="field w-auto px-3 text-sm"
        >
          <option value="">标记状态</option>
          {statusOptions.map((option) => (
            <option key={option} value={option}>
              {statusLabels[option]}
            </option>
          ))}
        </select>
      </div>
    </article>
  );
}
