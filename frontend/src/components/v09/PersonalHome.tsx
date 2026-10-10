"use client";

import { SessionBoundary } from "@/components/v09/SessionBoundary";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { myOverview, type V09Overview } from "@/lib/v09-api";
import { PersonalItemCard } from "@/components/v09/PersonalItemCard";
import { useSessionToken } from "@/lib/use-session";

export function PersonalHome() {
  return <SessionBoundary><PersonalHomeSession /></SessionBoundary>;
}

function PersonalHomeSession() {
  const router = useRouter();
  const [overview, setOverview] = useState<V09Overview | null>(null);
  const token = useSessionToken();
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!token) return;
    myOverview()
      .then(setOverview)
      .catch(() => setOverview(null))
      .finally(() => setLoaded(true));
  }, [token]);

  if (token && !loaded) return null;
  if (!token || !overview) {
    return (
      <section className="container-page py-6">
        <div className="panel-soft flex flex-wrap items-center justify-between gap-3 p-5">
          <div>
            <p className="font-semibold text-ink">我的竞赛</p>
            <p className="mt-1 text-sm text-muted">登录后按学校、学院、专业和方向筛选“现在适合关注”的赛事与截止时间。</p>
          </div>
          <Link href="/login" className="button-primary">登录 / 注册</Link>
        </div>
      </section>
    );
  }
  if (!overview.profile_complete) {
    return (
      <section className="container-page py-6">
        <div className="panel-soft flex flex-wrap items-center justify-between gap-3 p-5">
          <div>
            <p className="font-semibold text-ink">欢迎！先完成你的竞赛画像</p>
            <p className="mt-1 text-sm text-muted">学校 → 学院 → 专业 → 年级 → 感兴趣方向，约1分钟。</p>
          </div>
          <Link href="/onboarding" className="button-primary">开始设置</Link>
        </div>
      </section>
    );
  }
  const profile = overview.profile;
  return (
    <section className="container-page py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="label">My Competitions</p>
          <h2 className="mt-1 text-2xl font-semibold text-ink">
            你好，{profile?.university_name ?? "同学"}
            {profile?.college_name ? ` · ${profile.college_name}` : ""}
            {profile?.grade ? ` · ${profile.grade}` : ""}
          </h2>
          <p className="mt-1 text-sm text-muted">以下结果来自事实筛选：状态、方向标签、学校/学院通知与截止时间，不含平台评分。</p>
        </div>
        <Link href="/my-competitions" className="button-secondary">进入我的竞赛工作区</Link>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <span className="badge">我的近期截止 {overview.counts.upcoming_deadline ?? 0}</span>
        <span className="badge">正在报名 {overview.counts.now_available ?? 0}</span>
        {overview.counts.school_notices ? <span className="badge">我的学校通知 {overview.counts.school_notices}</span> : null}
      </div>
      <div className="mt-5 grid gap-6 lg:grid-cols-2">
        <Block title="我的近期截止" count={overview.counts.upcoming_deadline ?? 0}>
          {overview.upcoming_deadline.slice(0, 4).map((item) => (
            <PersonalItemCard key={item.competition_id} item={item} onChanged={() => router.refresh()} />
          ))}
        </Block>
        <Block title="现在可以参加" count={overview.counts.now_available ?? 0}>
          {overview.now_available.slice(0, 4).map((item) => (
            <PersonalItemCard key={item.competition_id} item={item} onChanged={() => router.refresh()} />
          ))}
        </Block>
      </div>
    </section>
  );
}

function Block({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold text-ink">{title}</h3>
        <span className="badge">{count}</span>
      </div>
      {children}
    </div>
  );
}
