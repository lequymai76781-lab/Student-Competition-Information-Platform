import { ArrowRight, CalendarDays, CircleDot, Clock3, ListFilter } from "lucide-react";
import Link from "next/link";

import { DemoBadge } from "@/components/DemoBadge";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { TagPill } from "@/components/TagPill";
import { getCompetitions } from "@/lib/api";
import { daysUntil, formatDate, freshnessDate, freshnessLabel } from "@/lib/format";
import type { CompetitionListItem } from "@/lib/types";
import { PersonalCalendar } from "@/components/v09/PersonalCalendar";

type CalendarPageProps = {
  searchParams?: Promise<{ university_id?: string; college_id?: string }> | { university_id?: string; college_id?: string };
};

export default async function CalendarPage({ searchParams }: CalendarPageProps) {
  const profile = await Promise.resolve(searchParams ?? {});
  const competitions = (await getCompetitions({
    sort: "deadline",
    limit: 100,
    university_id: profile.university_id,
    college_id: profile.college_id
  })).filter((item) => item.action_deadline);
  const monthLabel = new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", timeZone: "Asia/Shanghai" }).format(new Date());
  const upcoming = competitions.slice(0, 4);

  return (
    <>
      <PageHeader
        eyebrow="Competition Calendar"
        title="竞赛日历"
        description="只展示已有来源依据的报名、作品提交和比赛节点；无日期记录不会进入日历。"
        icon={CalendarDays}
      />

      <section className="container-page grid gap-6 py-8 lg:grid-cols-[300px_1fr]">
        <aside className="grid content-start gap-4 lg:sticky lg:top-24">
          <PersonalCalendar />
          <div className="panel p-5">
            <p className="label">当前月份</p>
            <h2 className="mt-2 text-2xl font-semibold text-ink">{monthLabel}</h2>
            <div className="mt-5 grid gap-3 text-sm text-muted">
              <Legend color="bg-blue-600" label="报名开始" />
              <Legend color="bg-amber-600" label="报名截止" />
              <Legend color="bg-emerald-600" label="初赛 / 决赛" />
            </div>
          </div>

          <div className="panel-soft p-5">
            <div className="mb-4 flex items-center gap-2">
              <ListFilter aria-hidden className="h-5 w-5 text-accent" />
              <h2 className="text-lg font-semibold text-ink">本月重点</h2>
            </div>
            <div className="divide-y divide-line">
              {upcoming.map((competition) => (
                <Link key={competition.id} href={detailHref(competition.id, profile.university_id, profile.college_id)} className="block py-3 text-sm transition duration-200 hover:text-accent">
                  <span className="block font-medium text-ink">{competition.short_name ?? competition.name}</span>
                  <span className="mt-1 block text-muted">{daysUntil(competition.action_deadline)}</span>
                </Link>
              ))}
            </div>
          </div>
        </aside>

        <div className="panel overflow-hidden">
          <div className="flex flex-col gap-3 border-b border-line p-5 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="label">Timeline</p>
              <h2 className="mt-1 text-xl font-semibold text-ink">重要节点</h2>
            </div>
            <span className="badge">{competitions.length} 个节点</span>
          </div>
          <div className="divide-y divide-line">
            {competitions.map((competition) => (
              <TimelineRow key={competition.id} competition={competition} universityId={profile.university_id} collegeId={profile.college_id} />
            ))}
          </div>
        </div>
      </section>
    </>
  );
}

function TimelineRow({ competition, universityId, collegeId }: { competition: CompetitionListItem; universityId?: string; collegeId?: string }) {
  return (
    <Link href={detailHref(competition.id, universityId, collegeId)} className="grid gap-4 p-5 transition duration-200 hover:bg-paper md:grid-cols-[170px_1fr_190px]">
      <div>
        <div className="inline-flex min-h-10 items-center gap-2 rounded-md border border-orange-100 bg-orange-50 px-3 text-sm font-semibold text-orange-700">
          <Clock3 aria-hidden className="h-4 w-4" />
          {formatDate(competition.action_deadline)}
        </div>
        <p className="mt-2 text-xs font-medium text-muted">{daysUntil(competition.action_deadline)}</p>
      </div>

      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold text-ink">{competition.name}</h3>
          <StatusBadge status={competition.current_status ?? competition.status} />
          {competition.is_demo ? <DemoBadge /> : null}
        </div>
        <p className="mt-2 text-sm text-muted">
          {competition.category ?? "方向暂未核实"} · {competition.team_type ?? "参赛形式暂未核实"} · {competition.current_edition_name ?? "届次名称暂未核实"}
        </p>
        <p className="mt-2 text-xs text-muted">
          {competition.official_registration_deadline ? `官方：${formatDate(competition.official_registration_deadline)}` : "官方截止暂未核实"}
          {competition.university_registration_deadline ? ` · 学校：${formatDate(competition.university_registration_deadline)}` : ""}
          {competition.college_registration_deadline ? ` · 学院：${formatDate(competition.college_registration_deadline)}` : ""}
        </p>
        <p className="mt-1 text-xs text-muted">{freshnessDate(competition.edition_last_verified_at)} · {freshnessLabel(competition.freshness_status)}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {competition.tags.slice(0, 3).map((tag) => (
            <TagPill key={tag.id} label={tag.name} />
          ))}
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 text-sm text-muted md:justify-end">
        <span className="inline-flex items-center gap-2">
          <CircleDot aria-hidden className="h-4 w-4 text-orange-700" />
          {competition.action_deadline_label ?? (competition.current_status === "submission_open" ? "作品提交截止" : "报名截止")}
        </span>
        <ArrowRight aria-hidden className="h-4 w-4 text-quiet" />
      </div>
    </Link>
  );
}

function detailHref(id: number, universityId?: string, collegeId?: string) {
  const query = new URLSearchParams();
  if (universityId) query.set("university_id", universityId);
  if (collegeId) query.set("college_id", collegeId);
  return query.size ? `/competitions/${id}?${query.toString()}` : `/competitions/${id}`;
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex min-h-8 items-center gap-2">
      <span className={`h-3 w-3 rounded-sm ${color}`} />
      {label}
    </div>
  );
}
