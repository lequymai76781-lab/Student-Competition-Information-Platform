import { FileCheck2, ShieldCheck } from "lucide-react";
import Link from "next/link";

import type { CompetitionListItem } from "@/lib/types";
import { daysUntil, formatDate } from "@/lib/format";

type ActivityFeedProps = {
  competitions: CompetitionListItem[];
};

export function ActivityFeed({ competitions }: ActivityFeedProps) {
  const items = competitions.slice(0, 4).map((competition) => {
    const Icon = competition.is_official_verified ? FileCheck2 : ShieldCheck;
    return { competition, Icon };
  });

  return (
    <div className="panel-soft p-4 md:p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="label">核验动态</p>
          <h2 className="mt-1 text-xl font-semibold text-ink">已确认的报名窗口</h2>
        </div>
        <span className="badge">动态情报</span>
      </div>
      <div className="divide-y divide-line">
        {items.map(({ competition, Icon }) => (
          <Link key={competition.id} href={`/competitions/${competition.id}`} className="grid gap-3 py-4 transition duration-200 hover:bg-white/70 md:grid-cols-[1fr_auto] md:px-2">
            <span className="flex min-w-0 items-start gap-3">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-white text-accent shadow-sm">
                <Icon aria-hidden className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <strong className="block truncate text-sm text-ink">{competition.short_name ?? competition.name}</strong>
                <span className="mt-1 block text-sm text-muted">
                  报名截止 {competition.registration_deadline ? formatDate(competition.registration_deadline) : "待公布"}
                </span>
              </span>
            </span>
            <span className="text-sm font-medium text-amber-700 md:text-right">{daysUntil(competition.registration_deadline)}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
