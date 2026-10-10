"use client";

import { SessionBoundary } from "@/components/v09/SessionBoundary";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { PersonalItemCard } from "@/components/v09/PersonalItemCard";
import { LayoutDashboard } from "lucide-react";
import { myOverview, notifications, type V09Item, type V09Notification, type V09Overview } from "@/lib/v09-api";
import { useSessionToken } from "@/lib/use-session";
import { formatDate } from "@/lib/format";

export default function MyCompetitionsPage() {
  return <SessionBoundary><MyCompetitionsPageSession /></SessionBoundary>;
}

function MyCompetitionsPageSession() {
  const router = useRouter();
  const token = useSessionToken();
  const [overview, setOverview] = useState<V09Overview | null>(null);
  const [recent, setRecent] = useState<V09Notification[]>([]);
  const [state, setState] = useState<"loading" | "guest" | "done">("loading");

  function reload() {
    Promise.all([myOverview(), notifications()])
      .then(([nextOverview, notificationData]) => {
        setOverview(nextOverview);
        setRecent(notificationData.items.slice(0, 5));
      })
      .catch(() => setState("guest"))
      .finally(() => setState((value) => (value === "loading" ? "done" : value)));
  }

  useEffect(() => {
    if (!token) return;
    reload();
  }, [token]);

  if (token && state === "loading") return <p className="container-page py-16 text-center text-sm text-muted">加载中…</p>;
  if (!token || state === "guest" || !overview) {
    return (
      <>
        <PageHeader eyebrow="My Competitions" title="我的竞赛" description="请先登录。" icon={LayoutDashboard} />
        <section className="container-page flex justify-center py-10">
          <button type="button" className="button-primary" onClick={() => router.push("/login")}>
            去登录
          </button>
        </section>
      </>
    );
  }
  if (!overview.profile_complete) {
    return (
      <>
        <PageHeader eyebrow="My Competitions" title="我的竞赛" description="设置学校后，可以查看你的校内竞赛通知与截止时间。" icon={LayoutDashboard} />
        <section className="container-page flex justify-center py-10">
          <button type="button" className="button-primary" onClick={() => router.push("/onboarding")}>
            设置学校 / 专业
          </button>
        </section>
      </>
    );
  }
  const profile = overview.profile;
  return (
    <>
      <PageHeader
        eyebrow="My Competitions"
        title="我的竞赛工作区"
        description="基于事实的个人化筛选：当前状态、方向、学校/学院通知与你的有效截止时间。"
        icon={LayoutDashboard}
        action={
          <button type="button" className="button-secondary" onClick={() => router.push("/settings/profile")}>
            编辑资料
          </button>
        }
      />

      <section className="container-page py-8">
        <div className="panel-soft p-5">
          <p className="font-semibold text-ink">
            我的学校：{profile?.university_name ?? "未设置"} · 学院：{profile?.college_name ?? "未设置"} · 专业：
            {profile?.major_name ?? "未设置"} · 当前年级：{profile?.grade ?? "未设置"}
          </p>
          <p className="mt-1 text-xs text-muted">兴趣方向：{(profile?.interest_tags ?? []).join(" / ") || "未选择"}</p>
        </div>

        {recent.length > 0 ? (
          <div className="mt-8">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-ink">最近变化</h2>
              <span className="badge">{recent.length}</span>
            </div>
            <div className="panel divide-y divide-line">
              {recent.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => item.competition_id && router.push(`/competitions/${item.competition_id}`)}
                  className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-paper"
                >
                  <span>
                    <span className="block text-sm font-medium text-ink">{item.title}</span>
                    <span className="mt-0.5 block text-xs text-muted">{item.content}</span>
                  </span>
                  <span className="shrink-0 text-xs text-quiet">{item.created_at ? formatDate(item.created_at) : ""}</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <SectionGrid
          title="现在可以参加"
          count={overview.counts.now_available ?? 0}
          items={overview.now_available.slice(0, 12)}
          onChanged={reload}
        />
        <SectionGrid title="即将截止（你的有效截止）" count={overview.counts.upcoming_deadline ?? 0} items={overview.upcoming_deadline.slice(0, 12)} onChanged={reload} />
        <SectionGrid title="与你方向相关" count={overview.counts.direction_related ?? 0} items={overview.direction_related.slice(0, 12)} onChanged={reload} />
        <SectionGrid title="我的学校有通知" count={overview.counts.school_notices ?? 0} items={overview.school_notices.slice(0, 12)} onChanged={reload} />
        <SectionGrid title="我的学校竞赛目录" count={overview.counts.school_directory ?? 0} items={overview.school_directory.slice(0, 12)} onChanged={reload} />
        <SectionGrid title="我收藏的比赛" count={overview.counts.favorites ?? 0} items={overview.favorites} onChanged={reload} />
      </section>
    </>
  );
}

function SectionGrid({ title, count, items, onChanged }: { title: string; count: number; items: V09Item[]; onChanged: () => void }) {
  if (items.length === 0) return null;
  return (
    <div className="mt-8">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-ink">{title}</h2>
        <span className="badge">{count}</span>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        {items.map((item) => (
          <PersonalItemCard key={item.competition_id} item={item} onChanged={onChanged} />
        ))}
      </div>
    </div>
  );
}
