import {
  AlertTriangle,
  BarChart3,
  CalendarClock,
  CheckCircle2,
  DatabaseZap,
  FileCheck2,
  FileSearch,
  FileText,
  GraduationCap,
  Link2,
  ScanSearch,
  ShieldCheck
} from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { getCompetitionDiscoveryCoverage, getStats } from "@/lib/api";
import type { UniversityCompetitionDiscoveryProgress } from "@/lib/types";

export default async function DataEngineeringPage() {
  const [coverage, stats] = await Promise.all([getCompetitionDiscoveryCoverage(), getStats()]);
  const progress = coverage.progress;
  const totalUniversities = coverage.universities_985_total + coverage.universities_211_non_985_total;
  const totalScanned = coverage.scanned_985_count + coverage.scanned_211_non_985_count;
  const scanPercent = Math.round((totalScanned / totalUniversities) * 100);
  const currentOpen = stats.registration_open ?? coverage.current_registration_count;

  return (
    <>
      <PageHeader
        eyebrow="Data Engineering"
        title="211高校赛事雷达覆盖"
        description="目录覆盖与实际扫描分开统计；查看39所985和73所非985的211高校通知、来源与当前届次。"
        icon={DatabaseZap}
        action={
          <Link href="/competitions?source_scope=university_notice&year=2026" className="button-secondary">
            <GraduationCap aria-hidden className="h-4 w-4" />
            高校通知赛事
          </Link>
        }
      />

      <section className="section-band">
        <div className="container-page grid grid-cols-2 gap-4 py-6 lg:grid-cols-4 xl:grid-cols-8">
          <StatCard label="985高校目录" value={`${coverage.universities_985_seeded}/${coverage.universities_985_total}`} helper="目录覆盖" icon={GraduationCap} />
          <StatCard label="985实际扫描" value={`${coverage.scanned_985_count}/${coverage.universities_985_total}`} helper="Discovery覆盖" icon={ScanSearch} />
          <StatCard label="非985的211目录" value={`${coverage.universities_211_non_985_seeded}/${coverage.universities_211_non_985_total}`} helper="目录覆盖" icon={GraduationCap} />
          <StatCard label="非985的211扫描" value={`${coverage.scanned_211_non_985_count}/${coverage.universities_211_non_985_total}`} helper={`${scanPercent}% 总体完成`} icon={ScanSearch} />
          <StatCard label="有效线索高校" value={`${coverage.universities_with_leads}/${totalUniversities}`} helper={`${coverage.competition_leads} 条Lead`} icon={FileSearch} />
          <StatCard label="生成Competition" value={coverage.universities_with_matched_competitions} helper={`${coverage.new_competitions} 个新增对象`} icon={BarChart3} />
          <StatCard label="2026届次高校" value={coverage.universities_with_2026_editions} helper={`${coverage.edition_2026_count} 条Edition`} icon={CalendarClock} />
          <StatCard label="当前报名" value={currentOpen} helper="可行动届次" icon={CalendarClock} />
        </div>
      </section>

      <section className="container-page py-10">
        <div className="mb-5">
          <p className="label">V0.8.1 Discovery Recall</p>
          <h2 className="mt-1 text-2xl font-semibold text-ink">211赛事雷达修复与多通道发现</h2>
          <p className="mt-2 text-sm leading-6 text-muted">
            非985的211学校从V0.8的50所partial重新扫描；状态改为 Completed / Completed with Gaps / Partial / Failed / Blocked，
            并按 Sitemap、部门栏目、外部检索、公众号线索、已知赛事反向匹配 分通道统计成功数。
          </p>
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatCard label="211已扫描" value={`${coverage.scanned_211_non_985_count}/${coverage.universities_211_non_985_total}`} helper="本轮重跑范围" icon={ScanSearch} />
          <StatCard label="Completed" value={coverage.completed_211_non_985_count} helper="≥2种通道成功或完整部门扫描" icon={CheckCircle2} />
          <StatCard label="Completed with Gaps" value={coverage.completed_with_gaps_211_non_985_count ?? 0} helper="有通道成功但存在失败/受限" icon={AlertTriangle} />
          <StatCard label="Partial" value={coverage.partial_211_non_985_count} helper="通道执行不充分" icon={ScanSearch} />
          <StatCard label="Failed / Blocked" value={`${coverage.failed_211_non_985_count} / ${coverage.blocked_211_non_985_count}`} helper="失败或站点反爬" icon={ShieldCheck} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-7">
          <StatCard label="Sitemap成功" value={coverage.discovery_methods?.sitemap ?? 0} helper="学校数" icon={Link2} />
          <StatCard label="部门栏目成功" value={coverage.discovery_methods?.department_feed ?? 0} helper="教务处/团委/创新学院等" icon={FileText} />
          <StatCard label="外部检索成功" value={coverage.discovery_methods?.external_search ?? 0} helper="360/DDG/Bing" icon={FileSearch} />
          <StatCard label="站内搜索成功" value={coverage.discovery_methods?.site_search ?? 0} helper="不作为唯一通道" icon={ScanSearch} />
          <StatCard label="公众号线索成功" value={coverage.discovery_methods?.wechat ?? 0} helper="mp.weixin.qq.com" icon={Link2} />
          <StatCard label="反向匹配成功" value={coverage.discovery_methods?.reverse_match ?? 0} helper="已知赛事反查高校" icon={BarChart3} />
          <StatCard label="导航发现成功" value={coverage.discovery_methods?.navigation ?? 0} helper="首页栏目入口" icon={GraduationCap} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-6">
          <StatCard label="Lead" value={coverage.competition_leads} helper="可核验线索" icon={FileSearch} />
          <StatCard label="Matched Competition" value={coverage.matched_competitions} helper="已匹配已有赛事" icon={CheckCircle2} />
          <StatCard label="University Relations" value={coverage.university_relations ?? 0} helper="高校-赛事-届次关系" icon={Link2} />
          <StatCard label="2026 Edition" value={coverage.edition_2026_count} helper="2026届次证据" icon={CalendarClock} />
          <StatCard label="内部Deadline" value={coverage.internal_deadlines ?? 0} helper="校内截止字段" icon={CalendarClock} />
          <StatCard label="当前可行动" value={coverage.current_registration_count} helper="报名/提交中" icon={FileCheck2} />
        </div>
      </section>

      <section className="container-page py-10">
        <div className="mb-5">
          <p className="label">V0.7.1 Acceptance</p>
          <h2 className="mt-1 text-2xl font-semibold text-ink">赛事事实与通知质量</h2>
          <p className="mt-2 text-sm leading-6 text-muted">统计仅陈述已落库字段和通知类型，不将搜索摘要当作最终事实来源。</p>
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <StatCard label="有赛事简介" value={stats.competitions_with_description ?? 0} helper="保留描述来源" icon={FileText} />
          <StatCard label="有主办单位" value={stats.competitions_with_organizer ?? 0} helper="字段级事实" icon={ShieldCheck} />
          <StatCard label="有赛事官网" value={stats.competitions_with_official_website ?? 0} helper="直接链接" icon={Link2} />
          <StatCard label="有创办年份" value={stats.competitions_with_founded_year ?? 0} helper="不按届数反推" icon={CalendarClock} />
          <StatCard label="字段事实来源" value={stats.field_fact_sources ?? 0} helper="可逐字段追溯" icon={FileCheck2} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="报名通知" value={stats.registration_notice_count ?? 0} helper="参与截止解析" icon={CalendarClock} />
          <StatCard label="校内选拔" value={stats.internal_selection_count ?? 0} helper="参与截止解析" icon={GraduationCap} />
          <StatCard label="作品提交通知" value={stats.submission_notice_count ?? 0} helper="独立提交节点" icon={FileCheck2} />
          <StatCard label="非行动通知" value={stats.non_action_notice_count ?? 0} helper="不改变开放状态" icon={FileSearch} />
        </div>
        <div className="mt-4 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="详情资料达标" value={stats.detail_ready_competitions ?? 0} helper="Minimum Dataset" icon={CheckCircle2} />
          <StatCard label="有历史时间线" value={stats.competitions_with_history_timeline ?? 0} helper="来源可追溯" icon={CalendarClock} />
          <StatCard label="有参赛细则" value={stats.competitions_with_participation_requirements ?? 0} helper="资格与组队要求" icon={GraduationCap} />
          <StatCard label="有比赛流程" value={stats.competitions_with_competition_process ?? 0} helper="按实际赛制整理" icon={BarChart3} />
          <StatCard label="有作品要求" value={stats.competitions_with_submission_requirements ?? 0} helper="材料与提交内容" icon={FileText} />
          <StatCard label="有奖项设置" value={stats.competitions_with_award_settings ?? 0} helper="仅官方明确数据" icon={FileCheck2} />
          <StatCard label="有报名费用" value={stats.editions_with_fee_information ?? 0} helper="金额或费用说明" icon={Link2} />
          <StatCard label="字段事实来源" value={stats.field_fact_sources ?? 0} helper="后台逐字段保留" icon={ShieldCheck} />
        </div>
      </section>

      <section className="container-page py-10">
        <div className="mb-5">
          <p className="label">Source Diversity</p>
          <h2 className="mt-1 text-2xl font-semibold text-ink">来源通道</h2>
        </div>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4 xl:grid-cols-6">
          <StatCard label="官网Lead" value={coverage.source_distribution.university_official ?? stats.university_official_leads ?? 0} helper="学校/学院站点" icon={GraduationCap} />
          <StatCard label="学院官网" value={coverage.source_distribution.college_official ?? 0} helper="关系来源计数" icon={FileCheck2} />
          <StatCard label="主办方官网" value={coverage.source_distribution.organizer_official ?? 0} helper="直接官方来源" icon={ShieldCheck} />
          <StatCard label="公众号Lead" value={coverage.wechat_leads} helper="本轮未作为事实源" icon={Link2} />
          <StatCard label="聚合平台" value={stats.third_party_platform_leads ?? 0} helper="仅进入发现层" icon={Link2} />
          <StatCard label="官方报名截止" value={stats.official_registration_deadline_count ?? 0} helper="字段级截止日期" icon={CalendarClock} />
        </div>
      </section>

      <section className="container-page pb-10">
        <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="label">Coverage Matrix</p>
            <h2 className="mt-1 text-2xl font-semibold text-ink">211高校竞赛发现矩阵</h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              已扫描 {totalScanned}/{totalUniversities} 所；985完成 {coverage.completed_985_count} 所，非985的211完成 {coverage.completed_211_non_985_count} 所。
            </p>
          </div>
          <span className="badge">未发现不等于不存在</span>
        </div>

        <div className="panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1320px] text-left text-sm">
              <thead className="border-b border-line bg-paper text-xs font-semibold uppercase text-quiet">
                <tr>
                  <th className="px-4 py-3">高校</th>
                  <th className="px-4 py-3">范围</th>
                  <th className="px-4 py-3">城市</th>
                  <th className="px-4 py-3">Discovery状态</th>
                  <th className="px-4 py-3">成功方式</th>
                  <th className="px-4 py-3 text-right">发现Lead</th>
                  <th className="px-4 py-3 text-right">匹配Competition</th>
                  <th className="px-4 py-3 text-right">新增Competition</th>
                  <th className="px-4 py-3 text-right">2026 Edition</th>
                  <th className="px-4 py-3 text-right">当前报名</th>
                  <th className="px-4 py-3 text-right">高校/学院通知</th>
                  <th className="px-4 py-3">最近扫描</th>
                  <th className="px-4 py-3">状态</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {progress.map((item) => (
                  <DiscoveryRow key={item.university_id} item={item} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </>
  );
}

function DiscoveryRow({ item }: { item: UniversityCompetitionDiscoveryProgress }) {
  const statusLabel = discoveryStatusLabel[item.discovery_status] ?? item.discovery_status;
  const healthy = item.discovery_status === "completed";
  const gaps = item.discovery_status === "completed_with_gaps";
  const warning = item.discovery_status === "partial";
  const methods = (item.methods_successful ?? [])
    .map((method) => methodLabel[method] ?? method)
    .filter(Boolean);

  return (
    <tr className="bg-white transition duration-200 hover:bg-paper">
      <td className="px-4 py-3">
        <div className="font-semibold text-ink">{item.university_name}</div>
        <div className="text-xs text-quiet">{item.short_name ?? "简称暂未核实"}</div>
      </td>
      <td className="px-4 py-3 text-xs font-medium text-muted">{item.scope === "211_non_985" ? "211（非985）" : "985"}</td>
      <td className="px-4 py-3 text-muted">
        {item.province ?? "暂未核实"} · {item.city ?? "暂未核实"}
      </td>
      <td className="px-4 py-3">
        <span className={healthy ? "tag-soft gap-1 border-emerald-200 bg-emerald-50 text-emerald-700" : gaps ? "tag-soft gap-1 border-sky-200 bg-sky-50 text-sky-700" : warning ? "tag-soft gap-1 border-amber-200 bg-amber-50 text-amber-700" : "tag-soft gap-1 border-slate-200 bg-slate-50 text-muted"}>
          {healthy ? <CheckCircle2 aria-hidden className="h-3.5 w-3.5" /> : <AlertTriangle aria-hidden className="h-3.5 w-3.5" />}
          {statusLabel}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-muted">
        <span className="block max-w-56 truncate" title={(item.methods_successful ?? []).join(", ")}>
          {methods.length > 0 ? methods.join(" · ") : (item.discovery_status === "not_started" ? "未开始" : "未成功")}
        </span>
      </td>
      <td className="px-4 py-3 text-right text-ink">{item.competition_leads}</td>
      <td className="px-4 py-3 text-right text-ink">{item.matched_competitions}</td>
      <td className="px-4 py-3 text-right text-ink">{item.new_competitions}</td>
      <td className="px-4 py-3 text-right text-ink">{item.edition_2026_count}</td>
      <td className="px-4 py-3 text-right text-ink">{item.current_registration_count}</td>
      <td className="px-4 py-3 text-right text-ink">{item.university_notice_count}/{item.college_notice_count}</td>
      <td className="px-4 py-3 text-xs text-muted">{formatCrawlTime(item.last_crawled_at)}</td>
      <td className="px-4 py-3">
        <span className="block max-w-64 truncate text-xs text-muted" title={item.reason ?? undefined}>
          {item.reason ?? "已记录"}
        </span>
      </td>
    </tr>
  );
}

const discoveryStatusLabel: Record<string, string> = {
  not_started: "未开始",
  discovering: "扫描中",
  completed: "已完成",
  completed_with_gaps: "完成但有缺口",
  partial: "部分完成",
  failed: "失败",
  blocked: "受限"
};

const methodLabel: Record<string, string> = {
  sitemap: "Sitemap",
  department_feed: "栏目",
  site_search: "站内搜索",
  external_search: "外部检索",
  wechat: "公众号",
  reverse_match: "反向匹配",
  navigation: "导航"
};

function formatCrawlTime(value?: string | null) {
  if (!value) return "尚未扫描";
  return new Date(value).toLocaleString("zh-CN", { hour12: false, timeZone: "Asia/Shanghai" });
}
