"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/PageHeader";
import { ShieldCheck } from "lucide-react";
import {
  adminCandidateFacts,
  adminCorrections,
  adminFeedback,
  adminLeads,
  adminReviewCorrection,
  adminReviewLead,
  adminSummary,
  adminUpdates,
  adminSupplements,
  adminReviewSupplement,
  type Supplement,
  type AdminCorrection, type AdminLead, type AdminCandidateFact, type AdminFeedback,
} from "@/lib/v09-api";
import { reviewStatusLabels } from "@/components/v09/ContributionHistory";
import type { CompetitionUpdateEvent } from "@/lib/types";
import { SessionBoundary } from "@/components/v09/SessionBoundary";
import { Pagination } from "@/components/v09/Pagination";
import { useSessionToken } from "@/lib/use-session";
import { usePrivateResource } from "@/lib/use-private-resource";
import { formatDate } from "@/lib/format";
import { stageFieldReviewOrigin } from "@/lib/field-review-api";

const tabs = ["用户纠错", "信息补充", "赛事线索", "事实变更", "候选事实", "Beta反馈"];

export default function AdminReviewPage() {
  return <SessionBoundary><AdminReviewSession /></SessionBoundary>;
}

const pageSize = 20;
type ReviewRow = AdminCorrection | AdminLead | CompetitionUpdateEvent | AdminCandidateFact | AdminFeedback | Supplement;

function AdminReviewSession() {
  const router = useRouter();
  const token = useSessionToken();
  const [tab, setTab] = useState("用户纠错");
  const [page, setPage] = useState(0);
  const [status, setReviewStatus] = useState("unfinished");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    const params = { limit: pageSize + 1, offset: page * pageSize };
    const request: Promise<ReviewRow[]> = tab === "用户纠错" ? adminCorrections(status, params)
      : tab === "信息补充" ? adminSupplements(status, params)
      : tab === "赛事线索" ? adminLeads(params)
      : tab === "事实变更" ? adminUpdates(params)
      : tab === "候选事实" ? adminCandidateFacts(params) : adminFeedback(params);
    const [summary, rows] = await Promise.all([adminSummary(), request]);
    return { summary, rows };
  }, [tab, page, status]);
  const { data, error: loadError, ready, reload: loadAll } = usePrivateResource(`${tab}-${page}-${status}`, load);
  const error = loadError || actionError;
  const denied = error.includes("管理员");
  const summary = data?.summary;
  const rows = data?.rows.slice(0, pageSize) ?? [];
  const corrections = (tab === "用户纠错" ? rows : []) as AdminCorrection[];
  const supplements = (tab === "信息补充" ? rows : []) as Supplement[];
  const leads = (tab === "赛事线索" ? rows : []) as AdminLead[];
  const updates = (tab === "事实变更" ? rows : []) as CompetitionUpdateEvent[];
  const candidateFacts = (tab === "候选事实" ? rows : []) as AdminCandidateFact[];
  const feedback = (tab === "Beta反馈" ? rows : []) as AdminFeedback[];

  useEffect(() => {
    if (!token && !window.localStorage.getItem("v09_token")) {
      router.replace("/login");
      return;
    }
  }, [token, router]);

  if (!token) return null;

  if (denied) {
    return (
      <>
        <PageHeader eyebrow="Admin" title="审核中心" description="需要管理员权限。" icon={ShieldCheck} />
        <section className="container-page py-10 text-center text-sm text-muted">
          当前账号没有管理员权限，请联系平台管理员。
        </section>
      </>
    );
  }

  async function runAction(action: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true); setActionError("");
    try { await action(); loadAll(); }
    catch (exc) { setActionError(exc instanceof Error ? exc.message : "审核操作失败，请重试。"); }
    finally { setBusy(false); }
  }
  async function actCorrection(row: AdminCorrection, status: string) {
    await runAction(() => adminReviewCorrection(row.id, status, notes[`correction-${row.id}`]));
  }
  async function actLead(id: number, status: string) {
    await runAction(() => adminReviewLead(id, status));
  }
  async function stageForFieldReview(kind: "correction" | "supplement", id: number) {
    await runAction(async () => {
      const candidate = await stageFieldReviewOrigin(kind, id);
      router.push(`/admin/field-review?candidate=${candidate.field_review_id}`);
    });
  }

  return (
    <>
      <PageHeader eyebrow="Admin Review Center" title="审核中心" description="赛事线索、事实变更、用户纠错与Beta反馈统一在这里处理。" icon={ShieldCheck} />
      <section className="container-page py-8">
        <Link href="/admin/field-review" className="button-primary mb-5">进入赛事字段审核</Link>
        {!ready ? <p role="status" className="mb-4 text-sm text-muted">正在加载审核数据…</p> : null}
        {error ? <div role="alert" className="mb-4 text-sm text-red-700">{error}<button type="button" onClick={loadAll} className="ml-3 underline">重新加载</button></div> : null}
        <fieldset disabled={busy} className="min-w-0">
        {summary ? (
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
            <Mini label="用户纠错待审" value={summary.corrections_pending ?? 0} />
            <Mini label="赛事线索待审" value={summary.leads_needs_review ?? 0} />
            <Mini label="候选事实待审" value={summary.candidate_facts_needs_review ?? 0} />
            <Mini label="赛事变更事件" value={summary.update_events ?? 0} />
            <Mini label="Beta反馈待处理" value={summary.beta_feedback_pending ?? 0} />
          </div>
        ) : null}
        <div className="mb-5 flex flex-wrap gap-2">
          {tabs.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => { setTab(item); setPage(0); setReviewStatus("unfinished"); setActionError(""); }}
              className={tab === item ? "button-primary min-h-9 px-3 text-sm" : "button-secondary min-h-9 px-3 text-sm"}
            >
              {item}
            </button>
          ))}
        </div>

        {tab === "用户纠错" || tab === "信息补充" ? <label className="mb-4 flex items-center gap-3 text-sm">
          <span>审核状态</span><select className="field w-auto" value={status} onChange={(event) => { setReviewStatus(event.target.value); setPage(0); setActionError(""); }}>
            <option value="unfinished">未完成</option>
            {(tab === "用户纠错" ? ["pending", "needs_more_evidence", "partially_approved", "approved", "rejected", "duplicate"] : ["pending", "needs_more_evidence", "partially_approved", "approved", "verified_pending_import", "rejected", "duplicate"]).map((value) => <option key={value} value={value}>{reviewStatusLabels[value]}</option>)}
            <option value="all">全部状态</option>
          </select>
        </label> : null}

        {ready && !loadError && tab === "用户纠错" ? (
          <List empty="暂无待审纠错">
            {corrections.map((row) => (
              <Row key={row.id} title={`${row.competition_name ?? "赛事"} · ${row.correction_type}`} meta={reviewStatusLabels[row.status] ?? row.status}>
                <p className="text-sm text-muted">{row.description}</p>
                {row.source_url && /^https?:\/\//.test(row.source_url) ? <a href={row.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block break-all text-sm text-accent">打开用户提供的来源</a> : null}
                {row.field_review_id ? <div className="mt-3"><Link href={`/admin/field-review?candidate=${row.field_review_id}`} className="button-primary text-sm">审核此纠错的字段候选</Link></div> : <>
                <label className="mt-3 grid gap-2"><span className="label">审核意见</span><textarea className="field py-2" value={notes[`correction-${row.id}`] ?? ""} onChange={(event) => setNotes({ ...notes, [`correction-${row.id}`]: event.target.value })} placeholder="记录核对依据或需要补充的内容" /></label>
                <p className="mt-2 text-xs text-muted">需修改正式资料时，转入字段审核后明确赛事、届次和候选值，再核验来源。</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <Action onClick={() => stageForFieldReview("correction", row.id)} label="转入字段审核" />
                  <Action onClick={() => actCorrection(row, "rejected")} label="拒绝" />
                  <Action onClick={() => actCorrection(row, "duplicate")} label="标记重复" />
                  <Action onClick={() => actCorrection(row, "needs_more_evidence")} label="需要更多证据" />
                </div>
                </>}
              </Row>
            ))}
          </List>
        ) : null}
        {ready && !loadError && tab === "信息补充" ? <List empty="暂无待处理的信息补充">
          {supplements.map((row) => <Row key={row.id} title={row.title} meta={reviewStatusLabels[row.status] ?? row.status}>
            <p className="whitespace-pre-wrap break-words text-sm text-muted">{row.description}</p>
            {row.source_url ? <a href={row.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-accent">打开提供的来源</a> : null}
            {row.field_review_id ? <div className="mt-3"><Link href={`/admin/field-review?candidate=${row.field_review_id}`} className="button-primary text-sm">审核此补充的字段候选</Link></div> : row.kind === "competition" ? <div className="mt-3"><Action label="转入字段审核" onClick={() => stageForFieldReview("supplement", row.id)} /></div> : <>
            <label className="mt-3 grid gap-2"><span className="label">审核意见（必填）</span><textarea className="field py-2" value={notes[`supplement-${row.id}`] ?? row.review_note ?? ""} onChange={(event) => setNotes({ ...notes, [`supplement-${row.id}`]: event.target.value })} /></label>
            <p className="mt-2 text-xs text-muted">核验后仍保留在待整理队列，不自动创建正式赛事或学校。</p>
            <div className="mt-3 flex flex-wrap gap-2">{["verified_pending_import", "needs_more_evidence", "rejected", "duplicate"].map((status) => <Action key={status} label={reviewStatusLabels[status]} onClick={() => runAction(() => adminReviewSupplement(row.id, status, notes[`supplement-${row.id}`] ?? row.review_note ?? ""))} />)}</div>
            </>}
          </Row>)}
        </List> : null}
        {ready && !loadError && tab === "赛事线索" ? (
          <List empty="暂无待审线索">
            {leads.map((row) => (
              <Row key={row.id} title={row.title} meta={`${row.classification ?? "未分类"}`}>
                <p className="text-xs text-muted break-all">{row.source_url}</p>
                <div className="mt-3 flex gap-2">
                  <Action onClick={() => actLead(row.id, "approved")} label="标记已核验" />
                  <Action onClick={() => actLead(row.id, "rejected")} label="标记噪声" />
                </div>
              </Row>
            ))}
          </List>
        ) : null}
        {ready && !loadError && tab === "事实变更" ? (
          <List empty="暂无变更事件">
            {updates.map((row) => (
              <Row key={row.id} title={`${row.competition_name ?? "赛事"} · ${row.event_type}`} meta={row.changed_at ? formatDate(row.changed_at) : undefined}>
                <p className="text-sm text-muted">
                  {row.old_value != null ? `${String(row.old_value)} → ` : ""}
                  {String(row.new_value ?? "")}
                </p>
                <p className="mt-1 text-xs text-muted break-all">{row.source_url}</p>
              </Row>
            ))}
          </List>
        ) : null}
        {ready && !loadError && tab === "候选事实" ? (
          <List empty="暂无候选事实">
            {candidateFacts.map((row) => (
              <Row key={row.id} title={row.field_name} meta={`${row.confidence ?? ""}`}>
                <p className="text-sm text-muted">{JSON.stringify(row.candidate_value)}</p>
                <p className="mt-1 text-xs text-muted break-all">{row.source_url}</p>
              </Row>
            ))}
          </List>
        ) : null}
        {ready && !loadError && tab === "Beta反馈" ? (
          <List empty="暂无反馈">
            {feedback.map((row) => (
              <Row key={row.id} title={`${row.category}`} meta={row.status}>
                <p className="text-sm text-muted">{row.content}</p>
                <p className="mt-1 text-xs text-muted">{row.url}</p>
              </Row>
            ))}
          </List>
        ) : null}
        <Pagination label="审核记录分页" page={page} hasNext={(data?.rows.length ?? 0) > pageSize} disabled={!ready || busy} onPage={setPage} />
        </fieldset>
      </section>
    </>
  );
}

function Mini({ label, value }: { label: string; value: number }) {
  return (
    <div className="panel-soft p-4">
      <p className="text-2xl font-semibold text-ink">{value}</p>
      <p className="mt-1 text-xs text-muted">{label}</p>
    </div>
  );
}

function List({ empty, children }: { empty: string; children: React.ReactNode }) {
  if (Array.isArray(children) && children.length === 0) {
    return <div className="panel-soft p-6 text-sm text-muted">{empty}</div>;
  }
  return <div className="grid gap-3">{children}</div>;
}

function Row({ title, meta, children }: { title: string; meta?: string; children: React.ReactNode }) {
  return (
    <div className="panel p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-semibold text-ink">{title}</p>
        {meta ? <span className="badge shrink-0">{meta}</span> : null}
      </div>
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Action({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="button-secondary min-h-8 px-3 text-xs">
      {label}
    </button>
  );
}
