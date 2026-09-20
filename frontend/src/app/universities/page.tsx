import { ArrowRight, Building2, Database, FileText, Filter, MapPin, ShieldCheck, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { PageHeader } from "@/components/PageHeader";
import { SectionTitle } from "@/components/SectionTitle";
import { getUniversities } from "@/lib/api";
import type { University } from "@/lib/types";

type UniversitiesPageProps = {
  searchParams?: Promise<UniversitySearchParams> | UniversitySearchParams;
};

type UniversitySearchParams = {
  keyword?: string;
  province?: string;
  year?: string;
  policy_type?: string;
};

const sourceHints = ["官方文件", "高校官网", "教务处", "研究生院", "学院通知"];

const policyTypeOptions = [
  { value: "recommendation", label: "保研 / 推免" },
  { value: "comprehensive_evaluation", label: "综测" },
  { value: "scholarship", label: "奖学金" },
  { value: "competition_reward", label: "竞赛奖励" },
  { value: "innovation_credit", label: "创新创业学分" }
];

export default async function UniversitiesPage({ searchParams }: UniversitiesPageProps) {
  const resolvedSearchParams = await Promise.resolve(searchParams ?? {});
  const universities = await getUniversities({
    keyword: resolvedSearchParams.keyword,
    province: resolvedSearchParams.province
  });

  const activeFilters = [
    resolvedSearchParams.keyword ? `学校：${resolvedSearchParams.keyword}` : null,
    resolvedSearchParams.province ? `省份：${resolvedSearchParams.province}` : null,
    resolvedSearchParams.year ? `年份：${resolvedSearchParams.year}` : null,
    resolvedSearchParams.policy_type ? `政策：${policyTypeOptions.find((item) => item.value === resolvedSearchParams.policy_type)?.label ?? resolvedSearchParams.policy_type}` : null
  ].filter(Boolean);

  return (
    <>
      <PageHeader
        eyebrow="University Policy Library"
        title="高校政策库"
        description="查看学校认可竞赛、综测政策、保研政策、竞赛奖励政策和创新创业政策。第一阶段重点建立政策索引与认可关系。"
        icon={Building2}
      />

      <section className="container-page grid gap-6 py-8 lg:grid-cols-[280px_1fr]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <form className="panel-soft grid gap-4 p-4" action="/universities">
            <div className="flex items-center gap-2 border-b border-line pb-3">
              <Filter aria-hidden className="h-4 w-4" />
              <h2 className="text-sm font-semibold text-ink">政策筛选</h2>
            </div>
            <label className="grid gap-2">
              <span className="label">学校</span>
              <input className="field" name="keyword" defaultValue={resolvedSearchParams.keyword} placeholder="武汉体育学院 / 武汉大学" />
            </label>
            <label className="grid gap-2">
              <span className="label">省份</span>
              <input className="field" name="province" defaultValue={resolvedSearchParams.province} placeholder="湖北 / 浙江 / 北京" />
            </label>
            <label className="grid gap-2">
              <span className="label">年份</span>
              <input className="field" name="year" defaultValue={resolvedSearchParams.year ?? "2026"} inputMode="numeric" />
            </label>
            <label className="grid gap-2">
              <span className="label">政策类型</span>
              <select className="field" name="policy_type" defaultValue={resolvedSearchParams.policy_type ?? ""}>
                <option value="">全部政策</option>
                {policyTypeOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button className="button-primary w-full" type="submit">
              <Filter aria-hidden className="h-4 w-4" />
              查询政策库
            </button>
          </form>

          <div className="panel mt-4 p-4">
            <div className="flex items-center gap-2">
              <ShieldCheck aria-hidden className="h-4 w-4 text-mint" />
              <h2 className="text-sm font-semibold text-ink">数据来源优先级</h2>
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {sourceHints.map((source) => (
                <span key={source} className="badge border-emerald-200 bg-emerald-50 text-emerald-700">
                  {source}
                </span>
              ))}
            </div>
            <p className="mt-3 text-sm leading-6 text-muted">详情页会展示政策原文、发布时间、核验状态和原始来源链接，便于学生自行复核。</p>
          </div>
        </aside>

        <div>
          <SectionTitle
            eyebrow="政策资料库"
            title="按学校查看政策档案"
            description="每所学校都是一个可继续展开的政策档案，后续会沉淀年份、政策类型、认可竞赛和证据片段。"
            action={<span className="badge">{universities.length} 所学校</span>}
          />

          {activeFilters.length ? (
            <div className="mb-5 flex flex-wrap gap-2">
              {activeFilters.map((filter) => (
                <span key={filter} className="badge border-blue-200 bg-blue-50 text-blue-700">
                  {filter}
                </span>
              ))}
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {universities.map((university) => (
              <UniversityCard key={university.id} university={university} />
            ))}
          </div>
        </div>
      </section>
    </>
  );
}

function UniversityCard({ university }: { university: University }) {
  const badges = [
    university.is_985 ? "985" : null,
    university.is_211 ? "211" : null,
    university.is_double_first_class ? "双一流" : null
  ].filter(Boolean);

  return (
    <Link href={`/universities/${university.id}`} className="panel-interactive block h-full p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label flex items-center gap-1">
            <MapPin aria-hidden className="h-3.5 w-3.5" />
            {university.province ?? "省份暂未核实"} · {university.city ?? "城市暂未核实"}
          </p>
          <h2 className="mt-2 text-lg font-semibold leading-7 text-ink">{university.name}</h2>
          <p className="mt-1 text-sm text-muted">{university.university_type ?? "高校类型暂未核实"}</p>
        </div>
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-blue-50 text-accent">
          <Building2 aria-hidden className="h-4 w-4" />
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {badges.length ? (
          badges.map((badge) => (
            <span key={badge} className="badge">
              {badge}
            </span>
          ))
        ) : (
          <span className="badge">普通本科</span>
        )}
      </div>

      <div className="mt-5 grid grid-cols-2 gap-2 text-sm">
        <MiniFact icon={FileText} label="政策档案" value="待展开" />
        <MiniFact icon={Database} label="认可关系" value="可追溯" />
      </div>

      <div className="mt-5 border-t border-line pt-4">
        <span className="inline-flex items-center gap-2 text-sm font-semibold text-accent transition duration-200 hover:text-blue-700">
          查看学校政策
          <ArrowRight aria-hidden className="h-4 w-4" />
        </span>
      </div>
    </Link>
  );
}

function MiniFact({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="rounded-md bg-paper p-3">
      <div className="flex items-center gap-2 text-muted">
        <Icon aria-hidden className="h-4 w-4" />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p className="mt-1 font-semibold text-ink">{value}</p>
    </div>
  );
}
