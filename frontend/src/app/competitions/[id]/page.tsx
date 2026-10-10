import { AlertTriangle, Award, Bell, Building2, CalendarDays, ExternalLink, FileText, GitBranch, History, ListChecks, Route, ShieldCheck, Tags, Upload, Users, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { TagPill } from "@/components/TagPill";
import { PersonalContext } from "@/components/v09/PersonalContext";
import { CorrectionForm } from "@/components/v09/CorrectionForm";
import { SchoolSelector } from "@/components/SchoolSelector";
import { getCompetition, getCompetitionRecognition, getCompetitionUpdates, getAllUniversities, getUniversity } from "@/lib/api";
import { formatDate, freshnessDate, freshnessLabel, statusLabel, verificationLabel, verificationTone } from "@/lib/format";
import type { CompetitionEdition, CompetitionFactRevision, CompetitionFactSource, CompetitionSource, DeadlineResolution, DetailFactItem, UniversityCompetitionNotice } from "@/lib/types";

type CompetitionDetailPageProps = {
  params: Promise<{ id: string }> | { id: string };
  searchParams?: Promise<{ university_id?: string; college_id?: string; edition_id?: string }> | { university_id?: string; college_id?: string; edition_id?: string };
};

export default async function CompetitionDetailPage({ params, searchParams }: CompetitionDetailPageProps) {
  const { id } = await Promise.resolve(params);
  const profile = await Promise.resolve(searchParams ?? {});
  if (!/^\d+$/.test(id)) notFound();
  const competition = await getCompetition(id, { university_id: profile.university_id, college_id: profile.college_id, edition_id: profile.edition_id });
  if (!competition) notFound();
  const [allRecognitions, updates, universities, selectedUniversity] = await Promise.all([
    getCompetitionRecognition(id),
    getCompetitionUpdates(id, competition.current_edition_id ?? profile.edition_id),
    getAllUniversities(),
    profile.university_id ? getUniversity(profile.university_id) : Promise.resolve(null)
  ]);
  const recognitions = allRecognitions.filter((item) => !profile.university_id || String(item.university_id) === profile.university_id);

  const aliases = unique([...(competition.aliases ?? []), ...(competition.former_names ?? [])]);
  const selectedNotices = profile.university_id
    ? competition.university_notices.filter((notice) => `${notice.university_id}` === profile.university_id)
    : competition.university_notices;
  const editions = [...competition.editions].sort((a, b) => b.year - a.year);
  const currentEdition = editions.find((edition) => edition.id === competition.current_edition_id);
  const sourceGroups = groupSources(competition.sources, competition.fact_sources);
  const overviewFacts = compactFacts([
    ["主办单位", competition.organizer],
    ["简称", competition.short_name],
    ["英文名称", competition.english_name],
    ["学科方向", competition.category],
    ["参赛形式", competition.team_type],
    ["团队人数", teamSize(competition.min_team_size, competition.max_team_size)],
    ["创办年份", competition.founded_year ? `${competition.founded_year}年` : null],
    [competition.action_deadline_label ?? "报名截止", safeDate(competition.action_deadline)],
    ["赛事范围", competition.competition_scope],
    ["国家或地区", competition.country_or_region],
    ["其他名称", aliases.join("、")]
  ]);
  const hasSchoolDeadline = hasDeadline(competition.deadline_resolution) || selectedNotices.length > 0 || Boolean(profile.university_id);
  const hasOrganization = Boolean(competition.organizer || competition.co_organizers?.length || competition.guiding_organizations?.length || competition.undertakers?.length || competition.official_account);
  const hasParticipation = Boolean(competition.target_students || competition.team_type || competition.min_team_size || competition.max_team_size || competition.participation_requirements?.length);
  const hasProcess = Boolean(competition.competition_process?.length || competition.competition_format || competition.typical_schedule);
  const verifiedHistory = (competition.history_timeline ?? []).filter((event) => isHttpUrl(event.source_url) && event.verification_status?.startsWith("verified"));
  const historySource = competition.fact_sources.find((source) => source.field_name === "development_history"
    && source.verification_status.startsWith("verified") && isHttpUrl(source.source_url));
  const displayStatus = competition.current_status ?? "unknown";
  const hasDescription = usefulDescription(competition.description);
  const freshnessWarning = ["due_for_check", "stale", "unknown"].includes(currentEdition?.freshness_status ?? "unknown");
  const deadlineRevisions = (competition.fact_revisions ?? []).filter((revision) => deadlineRevisionFields.has(revision.field_name)).slice(0, 3);

  return (
    <>
      <PageHeader
        eyebrow="赛事资料档案"
        title={competition.name}
        description={hasDescription ? firstSentence(competition.description!) : undefined}
        icon={ListChecks}
        action={<>
          {currentEdition?.official_registration_url ? <ExternalButton href={currentEdition.official_registration_url} label="报名入口" primary /> : null}
          {competition.official_website ? <ExternalButton href={competition.official_website} label="赛事官网" /> : null}
        </>}
      />

      <div className="container-page pt-4">
        <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
          报名、赛制及校内安排可能发生变化，请以赛事官方及所在学校最新通知为准。
        </p>
      </div>

      <main className="container-page grid max-w-5xl gap-6 py-8">
        <section className="panel-soft p-5" aria-label="选择学校查看通知与认定">
          <h2 className="font-semibold text-ink">查看我的学校通知与认定</h2>
          <form action={`/competitions/${id}`} className="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
            {profile.edition_id ? <input type="hidden" name="edition_id" value={profile.edition_id} /> : null}
            <SchoolSelector key={`${profile.university_id}-${profile.college_id}`} universities={universities} universityId={profile.university_id} collegeId={profile.college_id} selectedUniversity={selectedUniversity} />
            <button type="submit" className="button-secondary self-end">查看学校信息</button>
          </form>
          {profile.university_id && !recognitions.length ? <p className="mt-3 text-sm text-muted">暂未收录所选学校的认定文件；这不代表学校不认可该赛事。</p> : null}
        </section>
        <PersonalContext competitionId={Number(id)} editionId={competition.current_edition_id ?? (profile.edition_id ? Number(profile.edition_id) : undefined)} universityId={profile.university_id ? Number(profile.university_id) : undefined} collegeId={profile.college_id ? Number(profile.college_id) : undefined} />
        <section className="panel p-5" aria-labelledby="overview-title">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={displayStatus} />
            <span className={`badge ${verificationTone(competition.verification_status)}`}>
              <ShieldCheck aria-hidden className="h-3.5 w-3.5" />
              {verificationLabel(competition.verification_status)}
            </span>
            {freshnessWarning ? (
              <span className="badge border-amber-200 bg-amber-50 text-amber-800">
                <AlertTriangle aria-hidden className="h-3.5 w-3.5" />
                {freshnessLabel(currentEdition?.freshness_status)}
              </span>
            ) : null}
            {competition.competition_type !== "competition" ? <span className="badge">{competition.competition_type === "series" ? "系列赛事" : "子赛道"}</span> : null}
          </div>
          <SectionHeading id="overview-title" icon={ListChecks} title="赛事概览" className="mt-5" />
          {overviewFacts.length ? <FactGrid facts={overviewFacts} /> : null}
        </section>

        <section className="panel p-5" aria-labelledby="edition-title">
          <SectionHeading id="edition-title" icon={CalendarDays} title="当前届次" />
          {currentEdition ? <EditionRow edition={currentEdition} /> : <p className="mt-4 border-t border-line py-4 text-sm text-muted">当前届信息尚未公布。</p>}
          {deadlineRevisions.length ? <div className="mt-3 border-t border-line pt-3">{deadlineRevisions.map((revision) => <RevisionNotice key={revision.id} revision={revision} />)}</div> : null}
          {editions.length > 1 ? (
            <details className="mt-2 border-t border-line pt-4">
              <summary className="cursor-pointer text-sm font-semibold text-accent">查看其他届次（{editions.length - 1}）</summary>
              <div className="mt-3 divide-y divide-line">{editions.filter((edition) => edition.id !== currentEdition?.id).map((edition) => <EditionRow key={edition.id} edition={edition} />)}</div>
            </details>
          ) : null}
        </section>

        {hasDescription ? <section className="panel p-5" aria-labelledby="description-title"><SectionHeading id="description-title" icon={FileText} title="赛事简介" /><p className="mt-4 text-sm leading-7 text-muted">{competition.description}</p></section> : null}

        {hasParticipation ? (
          <section className="panel p-5" aria-labelledby="participation-title">
            <SectionHeading id="participation-title" icon={Users} title="谁可以参加" />
            <FactGrid facts={compactFacts([
              ["参赛对象", competition.target_students], ["个人或团队", competition.team_type], ["团队人数", teamSize(competition.min_team_size, competition.max_team_size)],
              ["跨校组队", hasVerifiedFact(competition.fact_sources, "is_cross_university_supported") && competition.is_cross_university_supported ? "明确允许" : null],
              ["跨专业组队", hasVerifiedFact(competition.fact_sources, "is_cross_major_supported") && competition.is_cross_major_supported ? "明确允许" : null]
            ])} />
            <DetailItems items={competition.participation_requirements} />
          </section>
        ) : null}

        {hasProcess ? (
          <section className="panel p-5" aria-labelledby="process-title">
            <SectionHeading id="process-title" icon={Route} title="如何参赛" />
            <FactGrid facts={compactFacts([["比赛形式", competition.competition_format], ["典型周期", competition.typical_schedule]])} />
            {competition.competition_process?.length ? <ol className="mt-4 border-t border-line">
              {competition.competition_process.map((step, index) => <li key={`${step.title}-${index}`} className="grid grid-cols-[32px_1fr] gap-3 border-b border-line py-4">
                <span className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-50 text-xs font-semibold text-accent">{index + 1}</span>
                <div><strong className="text-sm text-ink">{step.title}</strong>{step.description ? <p className="mt-1 text-sm leading-6 text-muted">{step.description}</p> : null}</div>
              </li>)}
            </ol> : null}
          </section>
        ) : null}

        {competition.submission_requirements?.length ? <section className="panel p-5" aria-labelledby="submission-title"><SectionHeading id="submission-title" icon={Upload} title="需要提交什么" /><DetailItems items={competition.submission_requirements} /></section> : null}

        {competition.tracks?.length ? <section className="panel p-5" aria-labelledby="tracks-title">
          <SectionHeading id="tracks-title" icon={GitBranch} title="赛道设置" />
          <div className="mt-4 divide-y divide-line border-t border-line">{competition.tracks.map((track) => <article key={track.id} className="py-4">
            <strong className="text-sm text-ink">{track.name}</strong>
            {track.description ? <p className="mt-1 text-sm leading-6 text-muted">{track.description}</p> : null}
            {isHttpUrl(track.source_url) ? <SourceLink href={track.source_url} label="查看赛道依据" /> : null}
          </article>)}</div>
        </section> : null}

        {competition.award_settings?.length ? <section className="panel p-5" aria-labelledby="awards-title"><SectionHeading id="awards-title" icon={Award} title="奖项设置" /><DetailItems items={competition.award_settings} /></section> : null}

        {hasSchoolDeadline ? <section className="panel p-5" aria-labelledby="deadline-title">
          <SectionHeading id="deadline-title" icon={CalendarDays} title="学校与学院截止" />
          <DeadlinePanel resolution={competition.deadline_resolution ?? { effective_deadline_type: "unverified" }} hasUniversitySelection={Boolean(profile.university_id)} />
          {selectedNotices.length ? <div className="mt-4 divide-y divide-line border-t border-line">{selectedNotices.map((notice) => <UniversityNoticeRow key={notice.id} notice={notice} />)}</div> : null}
        </section> : null}

        <section className="panel p-5" aria-labelledby="history-title">
          <SectionHeading id="history-title" icon={History} title="赛事历史" />
          <FactGrid facts={compactFacts([["创办年份", competition.founded_year ? `${competition.founded_year}年` : null], ["首次举办", competition.first_held_year ? `${competition.first_held_year}年` : null], ["举办频率", competition.frequency], ["已核实届数", competition.edition_count ? `${competition.edition_count}届` : null]])} />
          {editions.length ? <ol className="mt-4 border-l-2 border-blue-100 pl-5">{editions.map((edition) => <li key={`edition-${edition.id ?? edition.year}`} className="relative pb-5 last:pb-0">
            <span className="absolute -left-[25px] top-1 h-2 w-2 rounded-full bg-accent" />
            <p className="text-xs font-semibold text-accent">{edition.year}届</p>
            <strong className="mt-1 block text-sm text-ink">{edition.edition_name ?? `${edition.year}年届次`}</strong>
            {edition.host_location ? <p className="mt-1 text-sm leading-6 text-muted">举办地点：{edition.host_location}</p> : null}
            {isHttpUrl(edition.official_notice_url) ? <SourceLink href={edition.official_notice_url} label="官方通知" /> : null}
          </li>)}</ol> : null}
          {competition.development_history && historySource ? <div className="mt-4"><p className="whitespace-pre-wrap text-sm leading-7 text-muted">{competition.development_history}</p><SourceLink href={historySource.source_url} label="查看历史正文依据" /></div> : null}
          {verifiedHistory.length ? <><h3 className="mt-5 text-sm font-semibold text-ink">有来源的历史沿革</h3><ol className="mt-4 border-l-2 border-blue-100 pl-5">{verifiedHistory.map((event, index) => <li key={`${event.year}-${event.title}-${index}`} className="relative pb-5 last:pb-0">
            <span className="absolute -left-[25px] top-1 h-2 w-2 rounded-full bg-accent" /><p className="text-xs font-semibold text-accent">{event.year}</p><strong className="mt-1 block text-sm text-ink">{event.title}</strong>{event.description ? <p className="mt-1 text-sm leading-6 text-muted">{event.description}</p> : null}
            <SourceLink href={event.source_url!} label="查看历史依据" />
          </li>)}</ol></> : !(competition.development_history && historySource) ? <p className="mt-4 border-t border-line py-4 text-sm text-muted">赛事沿革尚待来源补全。已有届次见上方记录；可通过下方入口补充官方历史资料。</p> : null}
        </section>

        {hasOrganization ? <section className="panel p-5" aria-labelledby="organization-title"><SectionHeading id="organization-title" icon={Building2} title="组织机构" /><FactGrid facts={compactFacts([["主办单位", competition.organizer], ["联合主办", joinValues(competition.co_organizers)], ["指导单位", joinValues(competition.guiding_organizations)], ["承办单位", joinValues(competition.undertakers)], ["官方公众号", competition.official_account]])} /></section> : null}

        {competition.parent || competition.children?.length ? <section className="panel p-5" aria-labelledby="hierarchy-title">
          <SectionHeading id="hierarchy-title" icon={GitBranch} title="系列与子赛道" />
          {competition.parent ? <p className="mt-4 text-sm text-muted">所属系列：<Link href={`/competitions/${competition.parent.id}`} className="font-semibold text-accent">{competition.parent.name}</Link></p> : null}
          {competition.children?.length ? <div className="mt-3 grid sm:grid-cols-2">{competition.children.map((child) => <Link key={child.id} href={`/competitions/${child.id}`} className="border-b border-line py-3 text-sm font-medium text-ink hover:text-accent">{child.name}</Link>)}</div> : null}
        </section> : null}

        {recognitions.length ? <section className="panel p-5" aria-labelledby="policy-title">
          <SectionHeading id="policy-title" icon={Bell} title="高校目录收录" /><p className="mt-2 text-sm text-muted">以下内容只陈述高校或学院公开政策中的收录事实。</p>
          <div className="mt-4 divide-y divide-line border-t border-line">{recognitions.map((item) => <article key={item.id} className="py-4">
            <div className="flex flex-wrap items-center gap-2"><strong className="text-sm text-ink">{item.university_name}</strong>{item.college_name ? <span className="badge">{item.college_name}</span> : null}{item.recognition_level ? <span className="badge">{item.recognition_level}</span> : null}</div>
            <p className="mt-2 text-sm font-medium leading-6 text-ink">{item.policy_title}</p>{item.evidence_text ? <p className="mt-2 text-xs leading-5 text-muted">{item.evidence_text}</p> : null}{isHttpUrl(item.source_url) ? <SourceLink href={item.source_url} label="查看政策原文" /> : null}
          </article>)}</div>
        </section> : null}

        {competition.tags.length ? <section className="panel-soft p-5" aria-labelledby="tags-title"><SectionHeading id="tags-title" icon={Tags} title="方向标签" /><div className="mt-4 flex flex-wrap gap-2">{competition.tags.map((tag) => <TagPill key={tag.id} label={tag.name} />)}</div></section> : null}

        {sourceGroups.length ? <section className="panel p-5" aria-labelledby="sources-title">
          <SectionHeading id="sources-title" icon={FileText} title="资料来源" />
          <div className="mt-4 divide-y divide-line border-t border-line">{sourceGroups.map((source) => <article key={source.url} className="py-4">
            <div className="flex flex-wrap items-center gap-2"><strong className="text-sm text-ink">{source.name}</strong><span className="badge">{sourceTypeLabel(source.type)}</span></div>
            {source.fields.length ? <p className="mt-2 text-xs leading-5 text-muted">支持内容：{source.fields.join("、")}</p> : null}
            {isHttpUrl(source.url) ? <SourceLink href={source.url} label="打开来源" /> : <p className="mt-2 text-xs text-muted">本地归档来源</p>}
          </article>)}</div>
        </section> : null}
        {updates && updates.length > 0 ? (
          <section className="panel p-5" aria-labelledby="recent-updates-title">
            <SectionHeading id="recent-updates-title" icon={History} title="最近更新" />
            <div className="mt-3 divide-y divide-line">
              {updates.slice(0, 4).map((event) => (
                <div key={event.id} className="py-3 text-sm">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-ink">{updateTypeLabel(event.event_type)}</span>
                    <span className="shrink-0 text-xs text-muted">{event.changed_at ? formatDate(event.changed_at) : ""}</span>
                  </div>
                  {event.old_value != null && event.new_value != null ? (
                    <p className="mt-1 text-muted">
                      {String(event.old_value)} → {String(event.new_value)}
                    </p>
                  ) : null}
                  {event.notes ? <p className="mt-1 text-xs text-muted">{event.notes}</p> : null}
                  {event.source_url ? (
                    <a href={event.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-accent hover:underline">
                      查看来源
                    </a>
                  ) : null}
                </div>
              ))}
            </div>
          </section>
        ) : null}
        <CorrectionForm competitionId={Number(id)} editionId={currentEdition?.id ?? (profile.edition_id ? Number(profile.edition_id) : undefined)} />
      </main>
    </>
  );
}

function EditionRow({ edition }: { edition: CompetitionEdition }) {
  const facts = compactFacts([
    ["报名开始", safeDate(edition.registration_start)], ["报名截止", safeDate(edition.registration_deadline)], ["官方报名截止", safeDate(edition.official_registration_deadline)], ["校内最早截止", safeDate(edition.university_registration_deadline)],
    ["作品提交截止", safeDate(edition.submission_deadline)], ["官方作品截止", safeDate(edition.official_submission_deadline)], ["官方比赛日期", safeDate(edition.official_competition_date)], ["比赛开始", safeDate(edition.competition_start)], ["比赛结束", safeDate(edition.competition_end)], ["报名费用", feeLabel(edition.registration_fee, edition.fee_notes)]
  ]);
  return <article className="mt-4 border-t border-line py-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><div><strong className="text-sm text-ink">{edition.edition_name ?? `${edition.year}年届次`}</strong>{edition.edition_number ? <span className="ml-2 text-xs text-muted">第{edition.edition_number}届</span> : null}</div>{edition.current_status !== "unknown" ? <StatusBadge status={edition.current_status} /> : null}</div>
    {facts.length ? <FactGrid facts={facts} /> : <p className="mt-3 text-sm text-muted">该届详细时间尚未公布。</p>}
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted">{edition.current_status !== "unknown" ? <span className="mr-1">{statusLabel(edition.current_status)}</span> : null}<span>{freshnessDate(edition.last_verified_at)} · {freshnessLabel(edition.freshness_status)}</span>{edition.official_notice_url ? <ExternalButton href={edition.official_notice_url} label="官方通知" /> : null}{edition.official_registration_url ? <ExternalButton href={edition.official_registration_url} label="报名入口" primary /> : null}</div>
  </article>;
}

function RevisionNotice({ revision }: { revision: CompetitionFactRevision }) {
  const oldValue = revisionDate(revision.old_value);
  const newValue = revisionDate(revision.new_value);
  return <div className="flex flex-wrap items-center gap-2 py-2 text-sm"><AlertTriangle aria-hidden className="h-4 w-4 text-amber-700" /><strong className="text-ink">{factLabel[revision.field_name] ?? "截止时间"}已更新</strong><span className="text-muted">{oldValue} → {newValue}</span>{isHttpUrl(revision.source_url) ? <SourceLink href={revision.source_url} label="查看更新依据" /> : null}</div>;
}

function DeadlinePanel({ resolution, hasUniversitySelection }: { resolution: DeadlineResolution; hasUniversitySelection: boolean }) {
  const facts = compactFacts([["赛事官方截止", safeDate(resolution.official_deadline)], ["官方作品截止", safeDate(resolution.official_submission_deadline)], [resolution.university_name ? `${resolution.university_name}校内截止` : "学校内部截止", safeDate(resolution.university_deadline)], [resolution.college_name ? `${resolution.college_name}截止` : "学院内部截止", safeDate(resolution.college_deadline)], ["实际执行截止", safeDate(resolution.effective_deadline)], ["截止依据", resolution.effective_deadline_type !== "unverified" ? deadlineTypeLabel[resolution.effective_deadline_type] : null]]);
  const hasSchoolNotice = Boolean(resolution.university_deadline || resolution.college_deadline || resolution.notice_id);
  return <div className="mt-4">{facts.length ? <FactGrid facts={facts} /> : null}{hasUniversitySelection && !hasSchoolNotice ? <p className="border-t border-line py-4 text-sm text-amber-800">未发现所选学校的公开赛事通知，请以学校最新通知为准。</p> : null}{isHttpUrl(resolution.source_url) ? <SourceLink href={resolution.source_url} label="查看截止依据" /> : null}</div>;
}

function UniversityNoticeRow({ notice }: { notice: UniversityCompetitionNotice }) {
  const facts = compactFacts([["官方截止", safeDate(notice.official_registration_deadline)], ["学校截止", !notice.college_id ? safeDate(notice.internal_registration_deadline) : null], ["学院截止", safeDate(notice.college_registration_deadline)], ["作品提交截止", safeDate(notice.internal_submission_deadline ?? notice.college_submission_deadline)], ["校内开始", safeDate(notice.internal_registration_start)], ["组织单位", notice.organizing_department], ["联系人", notice.contact_person ?? notice.internal_contact], ["联系方式", notice.contact_method]]);
  return <article className="py-4"><div className="flex flex-wrap items-center gap-2"><strong className="text-sm text-ink">{notice.university_name}</strong>{notice.college_name ? <span className="badge">{notice.college_name}</span> : null}<span className="badge">{notice.edition_year}届</span><span className="badge">{noticeTypeLabel[notice.notice_type] ?? "赛事通知"}</span>{!notice.is_verified ? <span className="badge">待核验</span> : null}</div>{notice.notice_title ? <p className="mt-2 text-sm font-medium text-ink">{notice.notice_title}</p> : null}{notice.published_at ? <p className="mt-1 text-xs text-muted">通知发布：{safeDate(notice.published_at)}</p> : null}{facts.length ? <FactGrid facts={facts} /> : null}{isHttpUrl(notice.internal_notice_url) ? <SourceLink href={notice.internal_notice_url} label="打开高校通知" /> : <p className="mt-2 text-xs text-muted">原文保存在本地档案</p>}</article>;
}

function DetailItems({ items = [] }: { items?: DetailFactItem[] }) {
  if (!items.length) return null;
  return <dl className="mt-4 divide-y divide-line border-t border-line">{items.map((item, index) => <div key={`${item.label}-${index}`} className="grid gap-1 py-4 sm:grid-cols-[180px_1fr] sm:gap-4"><dt className="text-sm font-semibold text-ink">{item.label}</dt><dd className="text-sm leading-6 text-muted">{item.value}</dd></div>)}</dl>;
}

function FactGrid({ facts }: { facts: Array<[string, string]> }) {
  if (!facts.length) return null;
  return <dl className="mt-4 grid border-t border-line sm:grid-cols-2">{facts.map(([label, value]) => <div key={`${label}-${value}`} className="border-b border-line px-3 py-3 sm:odd:border-r"><dt className="label">{label}</dt><dd className="mt-1 break-words text-sm leading-6 text-ink">{value}</dd></div>)}</dl>;
}

function SectionHeading({ id, icon: Icon, title, className = "" }: { id: string; icon: LucideIcon; title: string; className?: string }) {
  return <div className={`flex items-center gap-2 ${className}`}><Icon aria-hidden className="h-5 w-5 text-accent" /><h2 id={id} className="text-lg font-semibold text-ink">{title}</h2></div>;
}

function ExternalButton({ href, label, primary = false }: { href: string; label: string; primary?: boolean }) {
  if (!isHttpUrl(href)) return null;
  return <a href={href} target="_blank" rel="noreferrer" className={primary ? "button-primary" : "button-secondary"}>{label}<ExternalLink aria-hidden className="h-4 w-4" /></a>;
}

function SourceLink({ href, label }: { href: string; label: string }) {
  if (!isHttpUrl(href)) return null;
  return <a href={href} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-xs font-semibold text-accent">{label}<ExternalLink aria-hidden className="h-3.5 w-3.5" /></a>;
}

type SourceGroup = { url: string; name: string; type: string; fields: string[] };

function groupSources(sources: CompetitionSource[], facts: CompetitionFactSource[]): SourceGroup[] {
  const groups = new Map<string, { url: string; name: string; type: string; fields: Set<string> }>();
  const upsert = (url: string, name: string | null | undefined, type: string, field?: string) => {
    const key = url || `${type}:${name ?? "local"}`;
    const current = groups.get(key) ?? { url, name: name ?? sourceTypeLabel(type), type, fields: new Set<string>() };
    if (field) current.fields.add(factLabel[field] ?? "其他赛事信息");
    groups.set(key, current);
  };
  sources.forEach((source) => upsert(source.source_url, source.source_name, source.source_type));
  facts.forEach((fact) => upsert(fact.source_url, fact.source_name, fact.source_type, fact.field_name));
  return [...groups.values()].map((group) => ({ ...group, fields: [...group.fields] })).sort((a, b) => sourcePriority(a.type) - sourcePriority(b.type) || a.name.localeCompare(b.name, "zh-CN"));
}

function compactFacts(values: Array<[string, string | null | undefined]>): Array<[string, string]> {
  return values.filter((item): item is [string, string] => Boolean(item[1]?.trim()) && item[1] !== "unknown");
}

function safeDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return formatDate(value);
}

function revisionDate(value: unknown) { return typeof value === "string" ? safeDate(value) ?? value : "暂未核实"; }

function usefulDescription(value?: string | null) { return Boolean(value && !value.includes("首次发现") && !value.startsWith("由已验证高校政策")); }
function firstSentence(value: string) { const sentence = value.split("。", 1)[0]; return sentence.length < value.length ? `${sentence}。` : value; }
function teamSize(min?: number | null, max?: number | null) { if (min && max) return min === max ? `${min}人` : `${min}-${max}人`; if (min) return `${min}人起`; if (max) return `最多${max}人`; return null; }
function feeLabel(fee?: number | null, notes?: string | null) { if (notes) return notes; if (fee === 0) return "免费"; return typeof fee === "number" ? `${fee}元` : null; }
function joinValues(values?: string[]) { return values?.length ? values.join("、") : null; }
function unique(values: string[]) { return values.filter((value, index) => value && values.indexOf(value) === index); }
function hasVerifiedFact(facts: CompetitionFactSource[], fieldName: string) { return facts.some((fact) => fact.field_name === fieldName && fact.verification_status.startsWith("verified")); }
function hasDeadline(resolution?: DeadlineResolution) { return Boolean(resolution?.official_deadline || resolution?.official_submission_deadline || resolution?.university_deadline || resolution?.college_deadline || resolution?.effective_deadline); }
function isHttpUrl(value?: string | null): value is string { return Boolean(value?.startsWith("http://") || value?.startsWith("https://")); }
function sourcePriority(type: string) { if (type.includes("government") || type.includes("organizer")) return 1; if (type.includes("university") || type.includes("college")) return 2; if (type.includes("official")) return 3; return 4; }
function sourceTypeLabel(type: string) { if (type.includes("government")) return "政府官方来源"; if (type.includes("organizer")) return "赛事官方来源"; if (type.includes("university")) return "高校官方来源"; if (type.includes("college")) return "学院官方来源"; if (type.includes("wechat")) return "官方公众号"; if (type.includes("github") || type.includes("discovery")) return "公开线索"; return "公开资料"; }

function updateTypeLabel(type: string) {
  const labels: Record<string, string> = {
    deadline_changed: "报名截止更新",
    submission_changed: "作品提交截止更新",
    competition_date_changed: "比赛时间更新",
    registration_opened: "开始报名",
    registration_closed: "报名结束",
    edition_created: "新增届次",
    notice_updated: "赛事通知更新",
    track_added: "新增赛道",
    other: "赛事信息更新"
  };
  return labels[type] ?? "赛事信息更新";
}
const deadlineTypeLabel: Record<string, string> = { college_registration_deadline: "学院公开通知", university_registration_deadline: "学校公开通知", official_registration_deadline: "赛事官方时间" };
const noticeTypeLabel: Record<string, string> = { registration_notice: "报名通知", internal_selection: "校内选拔", submission_notice: "作品提交", competition_announcement: "赛事公告", result_notice: "结果公示", award_news: "获奖新闻", training_notice: "培训通知", team_recruitment: "组队招募" };
const deadlineRevisionFields = new Set(["registration_deadline", "official_registration_deadline", "university_registration_deadline", "submission_deadline", "official_submission_deadline"]);
const factLabel: Record<string, string> = {
  name: "赛事名称", short_name: "赛事简称", english_name: "英文名称", former_names: "历史名称", description: "赛事简介", organizer: "主办单位", co_organizers: "联合主办", guiding_organizations: "指导单位", undertakers: "承办单位", official_website: "赛事官网", founded_year: "创办年份", first_held_year: "首次举办年份", frequency: "举办频率", competition_scope: "赛事范围", country_or_region: "国家或地区", category: "学科方向", target_students: "参赛对象", team_type: "组队形式", min_team_size: "最少团队人数", max_team_size: "最多团队人数", competition_format: "比赛形式", typical_schedule: "典型赛程", history_timeline: "历史沿革", participation_requirements: "参赛要求", competition_process: "比赛流程", submission_requirements: "提交材料", award_settings: "奖项设置", edition_name: "届次名称", edition_number: "届次编号", current_status: "当前届状态", registration_start: "报名开始时间", registration_deadline: "报名截止时间", official_registration_deadline: "官方报名截止", university_registration_deadline: "学校报名截止", submission_deadline: "作品提交截止", official_submission_deadline: "官方作品截止", official_competition_date: "官方比赛日期", competition_start: "比赛开始时间", competition_end: "比赛结束时间", official_registration_url: "官方报名入口", registration_fee: "报名费用", fee_notes: "费用说明"
};
