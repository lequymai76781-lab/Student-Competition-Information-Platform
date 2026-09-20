"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

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
} from "@/lib/v09-api";

const tabs = ["用户纠错", "赛事线索", "事实变更", "候选事实", "Beta反馈"];

export default function AdminReviewPage() {
  const router = useRouter();
  const [tab, setTab] = useState("用户纠错");
  const [summary, setSummary] = useState<Record<string, number> | null>(null);
  const [corrections, setCorrections] = useState<any[]>([]);
  const [leads, setLeads] = useState<any[]>([]);
  const [updates, setUpdates] = useState<any[]>([]);
  const [candidateFacts, setCandidateFacts] = useState<any[]>([]);
  const [feedback, setFeedback] = useState<any[]>([]);
  const [denied, setDenied] = useState(false);

  function loadAll() {
    adminSummary()
      .then(setSummary)
      .catch(() => setDenied(true));
    adminCorrections().then(setCorrections).catch(() => undefined);
    adminLeads().then(setLeads).catch(() => undefined);
    adminUpdates().then(setUpdates).catch(() => undefined);
    adminCandidateFacts().then(setCandidateFacts).catch(() => undefined);
    adminFeedback().then(setFeedback).catch(() => undefined);
  }

  useEffect(() => {
    if (!window.localStorage.getItem("v09_token")) {
      router.replace("/login");
      return;
    }
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (denied) {
    return (
      <>
        <PageHeader eyebrow="Admin" title="审核中心" description="需要管理员权限。" icon={ShieldCheck} />
        <section className="container-page py-10 text-center text-sm text-muted">
          当前账号不是管理员。测试管理员：admin@test.local / test123456
        </section>
      </>
    );
  }

  async function actCorrection(id: number, status: string) {
    await adminReviewCorrection(id, status, "前端审核操作");
    setCorrections((rows) => rows.filter((row) => row.id !== id));
  }
  async function actLead(id: number, status: string) {
    await adminReviewLead(id, status);
    setLeads((rows) => rows.filter((row) => row.id !== id));
  }

  return (
    <>
      <PageHeader eyebrow="Admin Review Center" title="审核中心" description="赛事线索、事实变更、用户纠错与Beta反馈统一在这里处理。" icon={ShieldCheck} />
      <section className="container-page py-8">
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
              onClick={() => setTab(item)}
              className={tab === item ? "button-primary min-h-9 px-3 text-sm" : "button-secondary min-h-9 px-3 text-sm"}
            >
              {item}
            </button>
          ))}
        </div>

        {tab === "用户纠错" ? (
          <List empty="暂无待审纠错">
            {corrections.map((row) => (
              <Row key={row.id} title={`${row.competition_name ?? "赛事"} · ${row.correction_type}`} meta={row.status}>
                <p className="text-sm text-muted">{row.description}</p>
                {row.source_url ? <p className="mt-1 text-xs text-accent break-all">{row.source_url}</p> : null}
                <div className="mt-3 flex flex-wrap gap-2">
                  <Action onClick={() => actCorrection(row.id, "approved")} label="批准" />
                  <Action onClick={() => actCorrection(row.id, "rejected")} label="拒绝" />
                  <Action onClick={() => actCorrection(row.id, "duplicate")} label="标记重复" />
                  <Action onClick={() => actCorrection(row.id, "needs_more_evidence")} label="需要更多证据" />
                </div>
              </Row>
            ))}
          </List>
        ) : null}
        {tab === "赛事线索" ? (
          <List empty="暂无待审线索">
            {leads.slice(0, 20).map((row) => (
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
        {tab === "事实变更" ? (
          <List empty="暂无变更事件">
            {updates.map((row) => (
              <Row key={row.id} title={`${row.competition_name ?? "赛事"} · ${row.event_type}`} meta={row.changed_at?.slice(0, 10)}>
                <p className="text-sm text-muted">
                  {row.old_value != null ? `${String(row.old_value)} → ` : ""}
                  {String(row.new_value ?? "")}
                </p>
                <p className="mt-1 text-xs text-muted break-all">{row.source_url}</p>
              </Row>
            ))}
          </List>
        ) : null}
        {tab === "候选事实" ? (
          <List empty="暂无候选事实">
            {candidateFacts.slice(0, 20).map((row) => (
              <Row key={row.id} title={row.field_name} meta={`${row.confidence ?? ""}`}>
                <p className="text-sm text-muted">{JSON.stringify(row.candidate_value)}</p>
                <p className="mt-1 text-xs text-muted break-all">{row.source_url}</p>
              </Row>
            ))}
          </List>
        ) : null}
        {tab === "Beta反馈" ? (
          <List empty="暂无反馈">
            {feedback.map((row) => (
              <Row key={row.id} title={`${row.category}`} meta={row.status}>
                <p className="text-sm text-muted">{row.content}</p>
                <p className="mt-1 text-xs text-muted">{row.url}</p>
              </Row>
            ))}
          </List>
        ) : null}
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
