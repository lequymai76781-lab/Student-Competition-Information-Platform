import { Filter, Search, SlidersHorizontal } from "lucide-react";
import Link from "next/link";

import { CompetitionCard } from "@/components/CompetitionCard";
import { EmptyState } from "@/components/EmptyState";
import { PageHeader } from "@/components/PageHeader";
import { TagPill } from "@/components/TagPill";
import { ViewToolbar } from "@/components/ViewToolbar";
import { SchoolSelector } from "@/components/SchoolSelector";
import { getCompetitions, getTags, getAllUniversities, getUniversity } from "@/lib/api";

const filterCategories = ["创新创业", "算法编程", "数学建模", "电子硬件", "机械土木", "文社科", "交叉学科", "学科竞赛", "综合"];

type CompetitionsPageProps = {
  searchParams?: Promise<CompetitionSearchParams> | CompetitionSearchParams;
};

type CompetitionSearchParams = {
  keyword?: string;
  category?: string;
  team_type?: string;
  status?: string;
  edition_status?: string;
  tag?: string;
  availability?: string;
  policy_coverage_min?: string;
  has_college_recognition?: string;
  competition_type?: string;
  source_scope?: string;
  university_id?: string;
  college_id?: string;
  year?: string;
  sort?: string;
  page?: string;
};

export default async function CompetitionsPage({ searchParams }: CompetitionsPageProps) {
  const resolvedSearchParams = await Promise.resolve(searchParams ?? {});
  const page = Math.max(1, Math.min(10000, Number.parseInt(resolvedSearchParams.page ?? "1", 10) || 1));
  const pageSize = 30;
  const invalidSchoolScope = (resolvedSearchParams.source_scope?.startsWith("my_") && !resolvedSearchParams.university_id)
    || (resolvedSearchParams.source_scope === "my_college_notice" && !resolvedSearchParams.college_id);
  const [rows, tags, universities, selectedUniversity] = await Promise.all([
    invalidSchoolScope ? Promise.resolve([]) :
    getCompetitions({
      keyword: resolvedSearchParams.keyword,
      category: resolvedSearchParams.category,
      team_type: resolvedSearchParams.team_type,
      status: resolvedSearchParams.status,
      edition_status: resolvedSearchParams.edition_status,
      tag: resolvedSearchParams.tag,
      availability: resolvedSearchParams.availability,
      policy_coverage_min: resolvedSearchParams.policy_coverage_min,
      has_college_recognition: resolvedSearchParams.has_college_recognition,
      competition_type: resolvedSearchParams.competition_type,
      source_scope: resolvedSearchParams.source_scope,
      university_id: resolvedSearchParams.university_id,
      college_id: resolvedSearchParams.college_id,
      year: resolvedSearchParams.year,
      sort: resolvedSearchParams.sort,
      limit: pageSize + 1,
      offset: (page - 1) * pageSize
    }),
    getTags(),
    getAllUniversities(),
    resolvedSearchParams.university_id ? getUniversity(resolvedSearchParams.university_id) : Promise.resolve(null)
  ]);
  const competitions = rows.slice(0, pageSize);
  function pageHref(target: number) {
    const query = new URLSearchParams();
    Object.entries(resolvedSearchParams).forEach(([key, value]) => { if (value && key !== "page") query.set(key, value); });
    query.set("page", String(target));
    return `/competitions?${query}`;
  }

  return (
    <>
      <PageHeader
        eyebrow="Competition Discovery"
        title="发现竞赛"
        description="按学科标签、参赛形式、真实届次状态和高校目录收录证据筛选竞赛。"
        icon={Search}
      />
      <section className="container-page grid gap-6 py-8 lg:grid-cols-[280px_1fr]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <form className="panel-soft grid gap-4 p-4" action="/competitions">
            <div className="flex items-center gap-2 border-b border-line pb-3">
              <SlidersHorizontal aria-hidden className="h-4 w-4 text-accent" />
              <h2 className="text-sm font-semibold text-ink">筛选器</h2>
            </div>
            <label className="grid gap-2">
              <span className="label">关键词</span>
              <input className="field" name="keyword" defaultValue={resolvedSearchParams.keyword} placeholder="比赛名 / 主办方 / 方向" />
            </label>
            <label className="grid gap-2">
              <span className="label">专业方向</span>
              <select className="field" name="category" defaultValue={resolvedSearchParams.category ?? ""}>
                <option value="">全部方向</option>
                {filterCategories.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>
            <label className="grid gap-2">
              <span className="label">学科 / 能力标签</span>
              <select className="field" name="tag" defaultValue={resolvedSearchParams.tag ?? ""}>
                <option value="">全部标签</option>
                {tags.map((tag) => <option key={tag.id} value={tag.name}>{tag.name}</option>)}
              </select>
            </label>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
              <label className="grid gap-2">
                <span className="label">个人 / 团队</span>
                <select className="field" name="team_type" defaultValue={resolvedSearchParams.team_type ?? ""}>
                  <option value="">不限</option>
                  <option value="个人赛">个人赛</option>
                  <option value="团队赛">团队赛</option>
                </select>
              </label>
              <label className="grid gap-2">
                <span className="label">届次状态</span>
                <select className="field" name="edition_status" defaultValue={resolvedSearchParams.edition_status ?? ""}>
                  <option value="">全部状态</option>
                  <option value="registration_open">报名中</option>
                  <option value="registration_upcoming">即将开始报名</option>
                  <option value="submission_open">作品提交中</option>
                  <option value="ongoing">进行中</option>
                  <option value="registration_closed">报名已截止</option>
                  <option value="finished">已结束</option>
                </select>
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
              <label className="grid gap-2">
                <span className="label">来源范围</span>
                <select className="field" name="source_scope" defaultValue={resolvedSearchParams.source_scope ?? ""}>
                  <option value="">全部赛事</option>
                  <option value="official_current">有官方当前届信息</option>
                  <option value="university_notice">有高校通知</option>
                  <option value="my_university_notice">有我的学校通知</option>
                  <option value="my_college_notice">有我的学院通知</option>
                  <option value="registration_open">当前报名中</option>
                </select>
              </label>
            </div>
            <SchoolSelector key={`${resolvedSearchParams.university_id}-${resolvedSearchParams.college_id}`} universities={universities} universityId={resolvedSearchParams.university_id} collegeId={resolvedSearchParams.college_id} selectedUniversity={selectedUniversity} />
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
              <label className="grid gap-2">
                <span className="label">可行动时间窗</span>
                <select className="field" name="availability" defaultValue={resolvedSearchParams.availability ?? ""}>
                  <option value="">不限</option>
                  <option value="next_30_days">未来30天</option>
                  <option value="next_90_days">未来90天</option>
                </select>
              </label>
              <label className="grid gap-2">
                <span className="label">赛事层级</span>
                <select className="field" name="competition_type" defaultValue={resolvedSearchParams.competition_type ?? ""}>
                  <option value="">全部</option>
                  <option value="series">系列赛事</option>
                  <option value="competition">独立赛事</option>
                  <option value="track">子赛道</option>
                </select>
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
              <label className="grid gap-2">
                <span className="label">目录收录证据</span>
                <select className="field" name="policy_coverage_min" defaultValue={resolvedSearchParams.policy_coverage_min ?? ""}>
                  <option value="">不限</option>
                  <option value="1">至少1份目录证据</option>
                  <option value="2">至少2份目录证据</option>
                </select>
              </label>
              <label className="grid gap-2">
                <span className="label">学院目录</span>
                <select className="field" name="has_college_recognition" defaultValue={resolvedSearchParams.has_college_recognition ?? ""}>
                  <option value="">不限</option>
                  <option value="true">已有学院目录证据</option>
                </select>
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-1">
              <label className="grid gap-2">
                <span className="label">比赛年份</span>
                <input className="field" name="year" defaultValue={resolvedSearchParams.year ?? ""} inputMode="numeric" placeholder="全部年份" />
              </label>
              <label className="grid gap-2">
                <span className="label">排序</span>
                <select className="field" name="sort" defaultValue={resolvedSearchParams.sort ?? "deadline"}>
                  <option value="deadline">即将截止</option>
                  <option value="latest">最近更新</option>
                  <option value="name">按名称</option>
                </select>
              </label>
            </div>
            <button className="button-primary w-full" type="submit">
              <Filter aria-hidden className="h-4 w-4" />
              应用筛选
            </button>
            <Link href="/competitions" className="text-center text-sm text-accent">清除筛选</Link>
          </form>
        </aside>

        <div>
          <ViewToolbar resultCount={competitions.length} />
          <p className="mt-2 text-xs text-muted">第 {page} 页 · 每页最多 {pageSize} 项。学校筛选用于查看校内截止；选择“有我的学校通知”可仅显示本校通知。</p>
          {invalidSchoolScope ? <p role="alert" className="mt-3 text-sm text-amber-800">请先选择学校；查看学院通知还需选择学院。</p> : null}
          <div className="mt-4 flex flex-wrap gap-2">
            {(resolvedSearchParams.tag ? [resolvedSearchParams.tag] : tags.slice(0, 8).map((tag) => tag.name)).map((tag) => (
              <TagPill key={tag} label={tag} />
            ))}
          </div>
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {competitions.map((competition) => (
              <CompetitionCard key={competition.id} competition={competition} universityId={resolvedSearchParams.university_id} collegeId={resolvedSearchParams.college_id} />
            ))}
          </div>
          {competitions.length === 0 ? (
            <div className="mt-6">
              <EmptyState title="没有找到匹配竞赛" description="可以放宽方向、参赛形式或届次状态筛选。" />
            </div>
          ) : null}
          <nav aria-label="竞赛分页" className="mt-6 flex justify-between gap-3">
            {page > 1 ? <Link href={pageHref(page - 1)} className="button-secondary">上一页</Link> : <span />}
            {rows.length > pageSize ? <Link href={pageHref(page + 1)} className="button-secondary">下一页</Link> : null}
          </nav>
        </div>
      </section>
    </>
  );
}
