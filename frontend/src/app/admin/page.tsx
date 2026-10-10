import { Bot, Database, ListTodo, Settings, ShieldAlert, ShieldCheck, TableProperties } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { getStats } from "@/lib/api";
import Link from "next/link";

const modules = [
  { title: "竞赛管理", description: "维护 Competition 与 CompetitionEdition。", icon: TableProperties },
  { title: "高校管理", description: "维护 University、College、Major 基础数据。", icon: Database },
  { title: "政策管理", description: "录入 UniversityPolicy 并关联原始来源。", icon: ShieldCheck },
  { title: "数据来源", description: "查看 CompetitionSource 和可信度评分。", icon: ListTodo },
  { title: "待复核信息", description: "区分发现线索和官方事实。", icon: ShieldAlert },
  { title: "爬虫任务", description: "预留 Firecrawl、RSSHub、MediaCrawler 和高校官网爬虫入口。", icon: Bot },
  { title: "数据统计", description: "查看收录、核验、关联覆盖率。", icon: Settings }
];

export default async function AdminPage() {
  const stats = await getStats();

  return (
    <>
      <PageHeader
        eyebrow="Admin"
        title="后台管理"
        description="第一阶段仅建立管理入口和数据概览，后续再补权限、表格编辑、爬虫调度和核验工作流。"
        icon={Settings}
      />
      <section className="container-page py-8">
        <Link href="/admin/review" className="button-primary mb-6">处理用户纠错与信息补充</Link>
        <Link href="/admin/document-policy" className="button-secondary mb-6 ml-3">来源文档分类与政策分析</Link>
        <Link href="/admin/review-learning" className="button-secondary mb-6 ml-3">人机共审学习状态</Link>
        <Link href="/admin/golden-set" className="button-secondary mb-6 ml-3">Golden Set 人工标注</Link>
        <div className="grid gap-4 md:grid-cols-4">
          <Metric label="比赛" value={stats.competitions} />
          <Metric label="高校" value={stats.universities} />
          <Metric label="政策" value={stats.policies} />
          <Metric label="认可关系" value={stats.recognitions} />
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {modules.map((module) => (
            <article key={module.title} className="panel-interactive p-5">
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-blue-50 text-accent">
                <module.icon aria-hidden className="h-5 w-5" />
              </span>
              <h2 className="mt-4 text-lg font-semibold text-ink">{module.title}</h2>
              <p className="mt-2 text-sm leading-6 text-muted">{module.description}</p>
              <button className="button-secondary mt-4" type="button">
                进入模块
              </button>
            </article>
          ))}
        </div>
      </section>
    </>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="panel-soft p-5">
      <p className="label">{label}</p>
      <p className="mt-2 text-3xl font-semibold text-ink">{value}</p>
    </div>
  );
}
