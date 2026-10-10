"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { myCorrections, mySupplements, type MyCorrection, type Supplement } from "@/lib/v09-api";
import { useSessionToken } from "@/lib/use-session";
import { usePrivateResource } from "@/lib/use-private-resource";
import { SessionBoundary } from "@/components/v09/SessionBoundary";
import { Pagination } from "@/components/v09/Pagination";

export const reviewStatusLabels: Record<string, string> = {
  pending: "待审核", approved: "审核通过", rejected: "未通过", duplicate: "重复记录",
  partially_approved: "部分通过，其余待处理",
  needs_more_evidence: "需要更多证据", verified_pending_import: "已核验，待整理入库",
};
const pageSize = 20;

export function ContributionHistory() {
  const token = useSessionToken();
  if (!token) return null;
  return <SessionBoundary><section className="panel p-5">
    <h2 className="font-semibold text-ink">我的提交</h2>
    <HistoryList kind="supplement" />
    <HistoryList kind="correction" />
  </section></SessionBoundary>;
}

function HistoryList({ kind }: { kind: "supplement" | "correction" }) {
  const [page, setPage] = useState(0);
  const title = kind === "supplement" ? "我的信息补充" : "我的纠错";
  const load = useCallback((): Promise<Array<Supplement | MyCorrection>> => {
    const params = { limit: pageSize + 1, offset: page * pageSize };
    return kind === "supplement" ? mySupplements(params) : myCorrections(params);
  }, [kind, page]);
  const { data, ready, error, reload } = usePrivateResource(`${kind}-${page}`, load);
  useEffect(() => {
    window.addEventListener("v09-contribution-change", reload);
    return () => window.removeEventListener("v09-contribution-change", reload);
  }, [reload]);
  const rows = data?.slice(0, pageSize) ?? [];
  return <section aria-label={title} className="mt-5 border-t border-line pt-4">
    <div className="flex items-center justify-between gap-3"><h3 className="font-semibold text-ink">{title}</h3><button type="button" onClick={reload} className="button-secondary" disabled={!ready}>刷新记录</button></div>
    {!ready ? <p role="status" className="mt-4 text-sm text-muted">正在加载提交记录…</p> : null}
    {error ? <p role="alert" className="mt-4 text-sm text-red-700">提交记录暂时无法加载，请重试。</p> : null}
    {ready && !error && !rows.length ? <p className="mt-4 text-sm text-muted">还没有提交记录。</p> : null}
    <div className="mt-4 divide-y divide-line">{rows.map((row) => <article key={row.id} className="py-4">
      <div className="flex flex-wrap justify-between gap-2"><h4 className="text-sm font-semibold text-ink">{"title" in row ? row.title : row.correction_type}</h4><span className="badge">{reviewStatusLabels[row.status] ?? row.status}</span></div>
      <p className="mt-2 whitespace-pre-wrap break-words text-sm text-muted">{row.description}</p>
      {row.review_note ? <p className="mt-2 text-sm text-ink">审核意见：{row.review_note}</p> : null}
      {"competition_id" in row ? <Link href={`/competitions/${row.competition_id}${row.competition_edition_id ? `?edition_id=${row.competition_edition_id}` : ""}`} className="mt-2 inline-block text-sm text-accent">查看相关赛事</Link> : null}
    </article>)}</div>
    <Pagination label={`${title}分页`} page={page} hasNext={(data?.length ?? 0) > pageSize} disabled={!ready} onPage={setPage} />
  </section>;
}
