import { ArrowRight, CalendarClock, Database, Library, Radar, Search, ShieldCheck, Tags, Trophy, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { CompetitionCard } from "@/components/CompetitionCard";
import { EmptyState } from "@/components/EmptyState";
import { HomeSearch } from "@/components/HomeSearch";
import { SectionTitle } from "@/components/SectionTitle";
import { StatCard } from "@/components/StatCard";
import { TagPill } from "@/components/TagPill";
import { PersonalHome } from "@/components/v09/PersonalHome";
import { SchoolSelector } from "@/components/SchoolSelector";
import { getCompetitions, getStats, getTags, getAllUniversities, getUniversity } from "@/lib/api";
import { formatDate, statusLabel } from "@/lib/format";
import type { CompetitionListItem } from "@/lib/types";

type HomePageProps = {
  searchParams?: Promise<{ university_id?: string; college_id?: string }> | { university_id?: string; college_id?: string };
};

export default async function HomePage({ searchParams }: HomePageProps) {
  const profile = await Promise.resolve(searchParams ?? {});
  const competitionHref = (filters: Record<string, string> = {}) => {
    const query = new URLSearchParams(filters);
    if (profile.university_id) query.set("university_id", profile.university_id);
    if (profile.college_id) query.set("college_id", profile.college_id);
    return `/competitions?${query.toString()}`;
  };
  const [stats, registrationOpen, registrationUpcoming, submissionOpen, closingWindow, tags, universities, selectedUniversity, mySchool] = await Promise.all([
    getStats(),
    getCompetitions({ edition_status: "registration_open", university_id: profile.university_id, college_id: profile.college_id, sort: "deadline", limit: 6 }),
    getCompetitions({ edition_status: "registration_upcoming", university_id: profile.university_id, college_id: profile.college_id, sort: "deadline", limit: 6 }),
    getCompetitions({ edition_status: "submission_open", university_id: profile.university_id, college_id: profile.college_id, sort: "deadline", limit: 6 }),
    getCompetitions({ availability: "next_30_days", university_id: profile.university_id, college_id: profile.college_id, sort: "deadline", limit: 12 }),
    getTags(),
    getAllUniversities(),
    profile.university_id ? getUniversity(profile.university_id) : Promise.resolve(null),
    profile.university_id
      ? getCompetitions({
          source_scope: profile.college_id ? "my_college_notice" : "my_university_notice",
          university_id: profile.university_id,
          college_id: profile.college_id,
          availability: "next_90_days",
          sort: "deadline",
          limit: 8
        })
      : Promise.resolve([])
  ]);
  const closingSoon = dedupe(closingWindow)
    .filter((item) => item.action_deadline)
    .sort((a, b) => new Date(a.action_deadline!).getTime() - new Date(b.action_deadline!).getTime());

  return (
    <>
      <section className="bg-white">
        <div className="container-page grid gap-10 py-10 lg:grid-cols-[1.35fr_0.65fr] lg:py-14">
          <div className="max-w-4xl">
            <p className="label mb-4">Student Competition Intelligence Platform</p>
            <h1 className="max-w-3xl text-3xl font-semibold leading-tight text-ink sm:text-4xl md:text-5xl">
              大学生竞赛情报平台
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-muted">
              汇集真实赛事、当前届次、报名节点、主办方和高校目录证据，每个事实都保留来源。
            </p>
            <HomeSearch />
            <div className="mt-7 flex flex-wrap gap-3">
              <Link href={competitionHref({ edition_status: "registration_open", sort: "deadline" })} className="button-primary">
                <CalendarClock aria-hidden className="h-4 w-4" />
                查看正在报名
              </Link>
              <Link href={competitionHref({ sort: "latest" })} className="button-secondary">
                <Search aria-hidden className="h-4 w-4" />
                浏览全部竞赛
              </Link>
            </div>
          </div>

          <div className="panel-soft grid content-start gap-1 p-3">
            <FeatureRow icon={Radar} title="发现与事实分离" description="第三方与社区信息先进入线索层。" tone="text-accent" />
            <FeatureRow icon={ShieldCheck} title="字段来源可追溯" description="主办方、日期和届次分别记录依据。" tone="text-mint" />
            <FeatureRow icon={Library} title="高校目录证据" description="保留学校、学院、年份和原始分级。" tone="text-orange-700" />
          </div>
        </div>
      </section>

      <PersonalHome />

      <section className="section-band">
        <div className="container-page grid grid-cols-2 gap-4 py-6 lg:grid-cols-6">
          <StatCard label="正在报名" value={stats.registration_open ?? 0} helper="按当前日期核对报名节点" icon={CalendarClock} />
          <StatCard label="近期截止" value={closingSoon.length} helper="未来30天内有节点" icon={CalendarClock} />
          <StatCard label="收录赛事" value={stats.competitions} helper="已核验真实竞赛对象" icon={Trophy} />
          <StatCard label="方向分类" value={tags.length} helper="按方向浏览赛事" icon={Tags} />
          <StatCard label="赛事届次" value={stats.editions ?? 0} helper="含当前与历史届次" icon={Database} />
          <StatCard label="收录高校" value={stats.universities} helper="通知与认定覆盖持续补充" icon={Library} />
        </div>
      </section>

      <section className="container-page py-10">
        <SectionTitle
          eyebrow="My University"
          title="我的学校近期赛事"
          description={selectedUniversity ? `优先展示 ${selectedUniversity.name} 已公开的赛事通知和校内节点。` : "选择学校后，优先展示该校公开赛事通知和更早的内部截止。"}
        />
        <form action="/" className="mb-6 grid gap-3 border-y border-line bg-white py-4 md:grid-cols-[1fr_1fr_auto]">
          <SchoolSelector key={`${profile.university_id}-${profile.college_id}`} universities={universities} universityId={profile.university_id} collegeId={profile.college_id} selectedUniversity={selectedUniversity} />
          <button className="button-secondary self-end" type="submit">应用学校信息</button>
        </form>
        {profile.university_id ? (
          mySchool.length ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {mySchool.slice(0, 4).map((competition) => <CompetitionCard key={competition.id} competition={competition} universityId={profile.university_id} collegeId={profile.college_id} />)}
            </div>
          ) : <EmptyState title="暂未发现该校公开赛事通知" description="公开检索未发现不代表学校没有组织、认可或参与该赛事。" />
        ) : <EmptyState title="尚未选择学校" description="选择学校后可查看对应校内通知和截止时间。" />}
      </section>

      <section className="section-band">
        <div className="container-page py-10">
        <SectionTitle
          eyebrow="Registration Open"
          title="正在报名"
          description="仅展示有已核实报名截止日期的当前届次。"
          action={<Link href={competitionHref({ edition_status: "registration_open" })} className="hidden items-center gap-2 text-sm font-semibold text-accent md:inline-flex">全部正在报名 <ArrowRight aria-hidden className="h-4 w-4" /></Link>}
        />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {registrationOpen.slice(0, 4).map((competition) => <CompetitionCard key={competition.id} competition={competition} universityId={profile.university_id} collegeId={profile.college_id} />)}
        </div>
        {registrationOpen.length === 0 ? <EmptyState title="暂无已核实的报名中届次" description="没有明确日期的记录不会进入本区域。" /> : null}
        </div>
      </section>

      <section className="container-page py-10">
        <SectionTitle
          eyebrow="Submission Open"
          title="作品提交中"
          description="报名已结束但仍可提交作品的届次单独展示。"
          action={<Link href={competitionHref({ edition_status: "submission_open" })} className="hidden items-center gap-2 text-sm font-semibold text-accent md:inline-flex">全部提交中赛事 <ArrowRight aria-hidden className="h-4 w-4" /></Link>}
        />
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {submissionOpen.slice(0, 4).map((competition) => <CompetitionCard key={competition.id} competition={competition} universityId={profile.university_id} collegeId={profile.college_id} />)}
        </div>
        {submissionOpen.length === 0 ? <EmptyState title="暂无已核实的作品提交中届次" description="报名中与作品提交中采用不同状态。" /> : null}
      </section>

      <section className="section-band">
        <div className="container-page grid gap-8 py-10 lg:grid-cols-2">
          <EditionList title="即将开始报名" eyebrow="Registration Upcoming" items={registrationUpcoming} empty="暂无已核实的报名开始节点" universityId={profile.university_id} collegeId={profile.college_id} />
          <EditionList title="近期截止" eyebrow="Closing Soon" items={closingSoon} empty="未来30天暂无已核实的截止节点" universityId={profile.university_id} collegeId={profile.college_id} />
        </div>
      </section>

      <section className="container-page py-10">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="label">Browse By Field</p>
            <h2 className="mt-1 text-2xl font-semibold text-ink">按方向浏览</h2>
          </div>
          <Link href={competitionHref()} className="text-sm font-semibold text-accent">查看全部竞赛</Link>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">
          {tags.slice(0, 18).map((tag) => (
            <Link key={tag.id} href={competitionHref({ tag: tag.name })}>
              <TagPill label={tag.name} />
            </Link>
          ))}
        </div>
      </section>
    </>
  );
}

function EditionList({ title, eyebrow, items, empty, universityId, collegeId }: { title: string; eyebrow: string; items: CompetitionListItem[]; empty: string; universityId?: string; collegeId?: string }) {
  return (
    <div>
      <p className="label">{eyebrow}</p>
      <h2 className="mt-1 text-2xl font-semibold text-ink">{title}</h2>
      <div className="mt-4 divide-y divide-line border-y border-line bg-white px-4">
        {items.slice(0, 6).map((competition) => (
          <Link key={competition.id} href={detailHref(competition.id, competition.current_edition_id, universityId, collegeId)} className="grid gap-2 py-4 transition hover:text-accent sm:grid-cols-[1fr_auto] sm:items-center">
            <span>
              <strong className="block text-sm text-ink">{competition.name}</strong>
              <span className="mt-1 block text-xs text-muted">{competition.current_edition_name ?? `${statusLabel(competition.current_status)}届次`}</span>
            </span>
            <span className="text-sm font-medium text-orange-700">{formatDate(competition.action_deadline)}</span>
          </Link>
        ))}
        {items.length === 0 ? <p className="py-5 text-sm text-muted">{empty}</p> : null}
      </div>
    </div>
  );
}

function detailHref(id: number, editionId?: number | null, universityId?: string, collegeId?: string) {
  const query = new URLSearchParams();
  if (editionId) query.set("edition_id", String(editionId));
  if (universityId) query.set("university_id", universityId);
  if (collegeId) query.set("college_id", collegeId);
  return query.size ? `/competitions/${id}?${query.toString()}` : `/competitions/${id}`;
}

function FeatureRow({ icon: Icon, title, description, tone }: { icon: LucideIcon; title: string; description: string; tone: string }) {
  return (
    <div className="grid grid-cols-[32px_1fr] gap-3 rounded-md px-3 py-4 transition duration-200 hover:bg-white">
      <span className={`mt-0.5 flex h-8 w-8 items-center justify-center rounded-md bg-white ${tone}`}>
        <Icon aria-hidden className="h-4 w-4" />
      </span>
      <div>
        <h2 className="text-sm font-semibold text-ink">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-muted">{description}</p>
      </div>
    </div>
  );
}

function dedupe(items: CompetitionListItem[]) {
  return Array.from(new Map(items.map((item) => [item.id, item])).values());
}
