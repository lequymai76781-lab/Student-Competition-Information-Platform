import { AlertTriangle, ArrowRight, Building2, CalendarClock, FileCheck2, Layers, Library, ShieldCheck, Users, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { daysUntil, formatDate, freshnessDate, freshnessLabel, verificationLabel, verificationTone } from "@/lib/format";
import type { CompetitionListItem } from "@/lib/types";

import { DemoBadge } from "./DemoBadge";
import { StatusBadge } from "./StatusBadge";
import { TagPill } from "./TagPill";

export function CompetitionCard({
  competition,
  universityId,
  collegeId
}: {
  competition: CompetitionListItem;
  universityId?: string | number;
  collegeId?: string | number;
}) {
  const actionDeadline = competition.action_deadline;
  const deadlineKind = competition.action_deadline_label ?? (competition.current_status === "submission_open" ? "作品提交截止" : "报名截止");
  const hierarchyLabel = competition.competition_type === "series" ? "系列赛事" : competition.competition_type === "track" ? "子赛道" : null;
  const displayStatus = competition.current_status ?? "unknown";
  const freshnessWarning = ["due_for_check", "stale", "unknown"].includes(competition.freshness_status ?? "unknown");

  return (
    <article className="panel-interactive flex h-full flex-col p-4 md:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge status={displayStatus} closingSoon={competition.registration_closing_soon} />
        <span className={`badge ${verificationTone(competition.verification_status)}`}>
          <ShieldCheck aria-hidden className="h-3.5 w-3.5" />
          {verificationLabel(competition.verification_status)}
        </span>
        {freshnessWarning ? (
          <span className="badge border-amber-200 bg-amber-50 text-amber-800">
            <AlertTriangle aria-hidden className="h-3.5 w-3.5" />
            {freshnessLabel(competition.freshness_status)}
          </span>
        ) : null}
        {hierarchyLabel ? <span className="badge">{hierarchyLabel}</span> : null}
        {competition.is_demo ? <DemoBadge /> : null}
      </div>

      <div className="mt-4 min-w-0">
        <h2 className="text-lg font-semibold leading-7 text-ink">{competition.name}</h2>
        {usefulDescription(competition.description) ? <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted">{competition.description}</p> : null}
      </div>

      <div className="mt-5 grid gap-3 text-sm text-muted">
        <Fact icon={Building2} label="主办方" value={competition.organizer} />
        <Fact icon={Layers} label="方向" value={competition.category} />
        <Fact icon={Users} label="参赛形式" value={competition.team_type} />
      </div>

      {actionDeadline ? (
        <div className="mt-5 border-y border-line py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="flex items-center gap-2 text-sm font-semibold text-ink">
              <CalendarClock aria-hidden className="h-4 w-4 text-orange-700" />
              {deadlineKind}
            </span>
            <span className="text-sm font-semibold text-orange-700">{daysUntil(actionDeadline)}</span>
          </div>
          <p className="mt-1 text-sm text-muted">
            {formatDate(actionDeadline)}
            {competition.current_edition_name ? ` · ${competition.current_edition_name}` : ""}
          </p>
          {competition.official_registration_deadline ? (
            <p className="mt-2 text-xs text-muted">赛事官方截止：{formatDate(competition.official_registration_deadline)}</p>
          ) : null}
          {competition.university_registration_deadline ? (
            <p className="mt-1 text-xs text-muted">学校截止：{formatDate(competition.university_registration_deadline)}</p>
          ) : null}
          {competition.college_registration_deadline ? (
            <p className="mt-1 text-xs font-medium text-orange-700">学院截止：{formatDate(competition.college_registration_deadline)}</p>
          ) : null}
        </div>
      ) : (
        <div className="mt-5 border-y border-line py-3 text-sm text-muted">当前届信息尚未公布</div>
      )}

      {(competition.university_inclusion_count ?? 0) > 0 ? <div className="mt-4 flex items-start gap-2 text-sm text-muted">
        <Library aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-mint" />
        <span>
          已被 {competition.university_inclusion_count ?? 0} 所高校、{competition.college_inclusion_count ?? 0} 个学院目录收录
        </span>
      </div> : null}

      {(competition.university_notice_count ?? 0) > 0 ? <div className="mt-2 flex items-start gap-2 text-sm text-muted">
        <FileCheck2 aria-hidden className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
        <span>
          {competition.university_notice_count ?? 0} 所高校通知 · {competition.university_source_count ?? 0} 条高校来源
        </span>
      </div> : null}

      <p className="mt-3 text-xs text-muted">{freshnessDate(competition.edition_last_verified_at)}</p>

      <div className="mt-4 flex flex-wrap gap-2">
        {competition.tags.slice(0, 4).map((tag) => (
          <TagPill key={tag.id} label={tag.name} />
        ))}
      </div>

      <Link href={detailHref(competition.id, universityId, collegeId, competition.current_edition_id)} className="mt-auto inline-flex min-h-11 items-center gap-2 pt-5 text-sm font-semibold text-accent transition duration-200 hover:text-blue-700">
        查看事实详情
        <ArrowRight aria-hidden className="h-4 w-4" />
      </Link>
    </article>
  );
}

function detailHref(id: number, universityId?: string | number, collegeId?: string | number, editionId?: number | null) {
  const query = new URLSearchParams();
  if (universityId) query.set("university_id", `${universityId}`);
  if (collegeId) query.set("college_id", `${collegeId}`);
  if (editionId) query.set("edition_id", String(editionId));
  return query.size ? `/competitions/${id}?${query.toString()}` : `/competitions/${id}`;
}

function Fact({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value?: string | null }) {
  if (!value || value === "unknown") return null;
  return (
    <div className="grid grid-cols-[18px_1fr] items-start gap-2">
      <Icon aria-hidden className="h-4 w-4 text-accent" />
      <span>{label}：{value}</span>
    </div>
  );
}

function usefulDescription(value?: string | null) {
  return Boolean(value && !value.includes("首次发现") && !value.startsWith("由已验证高校政策"));
}
