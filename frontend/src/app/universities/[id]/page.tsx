import { Award, Building2, CheckCircle2, ExternalLink, FileText, Link2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { DemoBadge } from "@/components/DemoBadge";
import { PageHeader } from "@/components/PageHeader";
import { getUniversity, getUniversityCompetitionPolicies, getUniversityPolicies } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { policyTypeLabel, recognitionStatusLabel } from "@/lib/taxonomy";
import type { CompetitionRecognition, UniversityPolicy } from "@/lib/types";

type UniversityDetailPageProps = {
  params: Promise<{ id: string }> | { id: string };
};

export default async function UniversityDetailPage({ params }: UniversityDetailPageProps) {
  const { id } = await Promise.resolve(params);
  const [university, policies, competitionPolicies] = await Promise.all([
    getUniversity(id),
    getUniversityPolicies(id),
    getUniversityCompetitionPolicies(id)
  ]);

  if (!university) {
    notFound();
  }

  const years = [...new Set(policies.map((policy) => policy.year).filter(Boolean))];
  const sourceCount = policies.filter((policy) => policy.source_url || policy.official_file_url).length;

  return (
    <>
      <PageHeader
        eyebrow="University Detail"
        title={university.name}
        description={`${university.province ?? ""}${university.city ?? ""} · ${university.university_type ?? "高校类型暂未核实"}`}
        icon={Building2}
        action={
          university.official_website ? (
            <Link href={university.official_website} className="button-secondary" target="_blank" rel="noreferrer">
              <ExternalLink aria-hidden className="h-4 w-4" />
              学校官网
            </Link>
          ) : null
        }
      />

      <section className="container-page grid gap-6 py-8 lg:grid-cols-[340px_1fr]">
        <aside className="grid content-start gap-6 lg:sticky lg:top-24">
          <div className="panel p-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="label">学校信息</p>
                <h2 className="mt-2 text-xl font-semibold text-ink">{university.short_name ?? university.name}</h2>
              </div>
              <span className="flex h-10 w-10 items-center justify-center rounded-md bg-blue-50 text-accent">
                <Building2 aria-hidden className="h-5 w-5" />
              </span>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              {university.is_985 ? <span className="badge">985</span> : null}
              {university.is_211 ? <span className="badge">211</span> : null}
              {university.is_double_first_class ? <span className="badge">双一流</span> : null}
              {!university.is_985 && !university.is_211 && !university.is_double_first_class ? <span className="badge">普通本科</span> : null}
            </div>
            <div className="mt-5 grid gap-3">
              <Info label="地区" value={`${university.province ?? "暂未核实"} · ${university.city ?? "暂未核实"}`} />
              <Info label="类型" value={university.university_type ?? "暂未核实"} />
              <Info label="政策年份" value={years.length ? years.join(" / ") : "暂未核实"} />
            </div>
          </div>

          <div className="panel-soft p-5">
            <div className="mb-4 flex items-center gap-2">
              <ShieldCheck aria-hidden className="h-5 w-5 text-mint" />
              <h2 className="text-lg font-semibold text-ink">核验概览</h2>
            </div>
            <div className="grid gap-3">
              <Info label="政策记录" value={`${policies.length} 条`} />
              <Info label="竞赛认可" value={`${competitionPolicies.length} 条`} />
              <Info label="来源链接" value={`${sourceCount} 条可访问`} />
            </div>
          </div>

          <div className="panel p-5">
            <p className="label">数据来源</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="badge border-emerald-200 bg-emerald-50 text-emerald-700">官方文件</span>
              <span className="badge border-blue-200 bg-blue-50 text-blue-700">高校官网</span>
              <span className="badge">教务处 / 研究生院</span>
            </div>
            <p className="mt-3 text-sm leading-6 text-muted">页面优先展示可点击原始来源。演示数据会明确标记，不能代替学校最新政策原文。</p>
          </div>
        </aside>

        <div className="grid gap-6">
          <div className="panel p-5">
            <div className="mb-4 flex items-center gap-2">
              <FileText aria-hidden className="h-5 w-5 text-accent" />
              <h2 className="text-xl font-semibold text-ink">最新政策</h2>
            </div>
            <div className="grid gap-3">
              {policies.map((policy) => (
                <PolicyCard key={policy.id} policy={policy} />
              ))}
              {policies.length === 0 ? <p className="text-sm text-muted">暂无政策记录。</p> : null}
            </div>
          </div>

          <div className="panel p-5">
            <div className="mb-4 flex items-center gap-2">
              <Link2 aria-hidden className="h-5 w-5 text-mint" />
              <h2 className="text-xl font-semibold text-ink">竞赛认可列表</h2>
            </div>
            <div className="grid gap-3">
              {competitionPolicies.map((item) => (
                <RecognitionCard key={item.id} item={item} />
              ))}
              {competitionPolicies.length === 0 ? <p className="text-sm text-muted">暂无竞赛认可记录。</p> : null}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}

function PolicyCard({ policy }: { policy: UniversityPolicy }) {
  return (
    <article className="rounded-lg border border-line bg-white p-4 transition duration-200 hover:border-slate-300 hover:bg-paper/40">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold text-ink">{policy.policy_name}</h3>
        <span className="badge border-blue-200 bg-blue-50 text-blue-700">{policyTypeLabel(policy.policy_type)}</span>
        {policy.is_verified ? (
          <span className="badge border-emerald-200 bg-emerald-50 text-emerald-700">
            <CheckCircle2 aria-hidden className="h-3.5 w-3.5" />
            已核验
          </span>
        ) : (
          <span className="badge">暂未核实</span>
        )}
        {policy.is_demo ? <DemoBadge /> : null}
      </div>
      <p className="mt-3 text-sm leading-6 text-muted">{policy.content ?? "政策摘要暂未核实。"}</p>
      <div className="mt-4 grid gap-2 text-sm md:grid-cols-3">
        <Info label="年份" value={policy.year ? `${policy.year}` : "暂未核实"} />
        <Info label="发布时间" value={formatDate(policy.published_at)} />
        <Info label="生效时间" value={formatDate(policy.effective_date)} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {policy.official_file_url ? (
          <SourceLink href={policy.official_file_url} label="政策原文" />
        ) : null}
        {policy.source_url ? (
          <SourceLink href={policy.source_url} label="原始来源" />
        ) : null}
        {!policy.official_file_url && !policy.source_url ? <span className="text-sm text-muted">原始来源暂未核实</span> : null}
      </div>
    </article>
  );
}

function RecognitionCard({ item }: { item: CompetitionRecognition }) {
  return (
    <article className="rounded-lg border border-line bg-white p-4 transition duration-200 hover:border-slate-300 hover:bg-paper/40">
      <div className="flex flex-wrap items-center gap-2">
        <Link href={`/competitions/${item.competition_id}`} className="font-semibold text-ink transition duration-200 hover:text-accent">
          {item.competition_name}
        </Link>
        <span className="badge border-emerald-200 bg-emerald-50 text-emerald-700">{recognitionStatusLabel(item.recognition_status)}</span>
        <span className="badge">{policyTypeLabel(item.usage_type)}</span>
        {item.recognized_level ? <span className="badge">{item.recognized_level}</span> : null}
        {item.is_demo ? <DemoBadge /> : null}
      </div>
      <p className="mt-3 text-sm leading-6 text-muted">{item.notes ?? "暂无说明"}</p>
      <div className="mt-4 rounded-md border border-line bg-paper p-3">
        <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-quiet">
          <Award aria-hidden className="h-3.5 w-3.5" />
          政策证据片段
        </div>
        <p className="text-sm leading-6 text-muted">{item.evidence_text ?? "政策证据片段暂未核实。"}</p>
      </div>
    </article>
  );
}

function SourceLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="button-secondary min-h-9 px-3" target="_blank" rel="noreferrer">
      <ExternalLink aria-hidden className="h-4 w-4" />
      {label}
    </Link>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-paper px-3 py-2">
      <p className="label">{label}</p>
      <p className="mt-1 text-sm font-medium leading-6 text-ink">{value}</p>
    </div>
  );
}
