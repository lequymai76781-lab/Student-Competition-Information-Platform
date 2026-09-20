import { Bell, BookmarkCheck, ClipboardCheck, LayoutDashboard, Medal } from "lucide-react";

import { PageHeader } from "@/components/PageHeader";

const sections = [
  { title: "收藏", value: "0", helper: "收藏比赛列表将在登录后启用", icon: BookmarkCheck },
  { title: "报名计划", value: "0", helper: "未来支持阶段、材料和队友管理", icon: ClipboardCheck },
  { title: "截止提醒", value: "0", helper: "预留邮件、站内和日历提醒", icon: Bell },
  { title: "获奖记录", value: "0", helper: "未来用于简历和保研材料整理", icon: Medal }
];

export default function DashboardPage() {
  return (
    <>
      <PageHeader
        eyebrow="My Competitions"
        title="我的竞赛"
        description="第一阶段仅建立 UI 骨架；登录、收藏、报名计划、提醒和获奖记录会在后续版本接入。"
        icon={LayoutDashboard}
      />
      <section className="container-page py-8">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {sections.map((section) => (
            <article key={section.title} className="panel-soft p-5">
              <span className="flex h-9 w-9 items-center justify-center rounded-md bg-white text-accent">
                <section.icon aria-hidden className="h-5 w-5" />
              </span>
              <p className="mt-4 text-3xl font-semibold text-ink">{section.value}</p>
              <h2 className="mt-2 font-semibold text-ink">{section.title}</h2>
              <p className="mt-2 text-sm leading-6 text-muted">{section.helper}</p>
            </article>
          ))}
        </div>
        <div className="panel mt-6 p-5">
          <p className="label">下一步功能</p>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <Task title="收藏竞赛" description="把 Favorite 模型接入登录用户。" />
            <Task title="报名计划" description="按比赛届次维护报名材料和节点。" />
            <Task title="截止提醒" description="对接邮件、短信或日历订阅。" />
          </div>
        </div>
      </section>
    </>
  );
}

function Task({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-md border border-line bg-paper p-4">
      <h3 className="font-semibold text-ink">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-muted">{description}</p>
    </div>
  );
}
