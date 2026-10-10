"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Pagination } from "@/components/v09/Pagination";
import { SessionBoundary } from "@/components/v09/SessionBoundary";
import { primaryDocumentTypes, primaryDocumentTypeLabels, type PrimaryDocumentType } from "@/lib/document-policy-api";
import { correctLearningExample, createLearningBatch, learningBatches, learningConfig, learningExamples, learningPerformance, type LearningExample, type LearningWindow } from "@/lib/review-learning-api";
import { usePrivateResource } from "@/lib/use-private-resource";
import { useSessionToken } from "@/lib/use-session";
const errors: Record<string, string> = { TITLE_AMBIGUOUS: "标题歧义", POLICY_FALSE_POSITIVE: "政策误判", POLICY_FALSE_NEGATIVE: "政策漏判", EDITION_CONFUSION: "届次混淆", SCHOOL_RELATION_CONFUSION: "学校关系混淆", SOURCE_TYPE_CONFUSION: "来源类型混淆", MULTI_LABEL_CONFUSION: "多标签混淆", UNKNOWN: "其他判断差异" };
const rate = (value: number | null | undefined, denominator: number | undefined) => `${value == null || !Number.isFinite(value) ? "暂无" : `${(value * 100).toFixed(1)}%`} · 分母 ${denominator ?? "暂无"}`;
const primaryLabel = (value?: string) => value && value in primaryDocumentTypeLabels ? primaryDocumentTypeLabels[value as PrimaryDocumentType] : "暂无";
export default function ReviewLearningPage() { return <SessionBoundary><LearningPage /></SessionBoundary>; }
function LearningPage() {
  const token = useSessionToken(); const router = useRouter();
  const [examplePage, setExamplePage] = useState(0);
  const config = usePrivateResource("learning-status-config", learningConfig);
  const load = useCallback(async () => {
    if (!config.data?.enabled) return null;
    const [performance, examples, batches] = await Promise.all([learningPerformance(), learningExamples(examplePage * 50), learningBatches()]);
    return { performance, examples, batches };
  }, [config.data?.enabled, examplePage]);
  const data = usePrivateResource(`learning-status-${Boolean(config.data?.enabled)}-${examplePage}`, load);
  const [threshold, setThreshold] = useState<100 | 300 | 500>(100);
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  useEffect(() => { if (!token && !window.localStorage.getItem("v09_token")) router.replace("/login?next=%2Fadmin%2Freview-learning"); }, [router, token]);
  async function createBatch() {
    if (busy) return; setBusy(true); setError(""); setMessage("");
    try { const result = await createLearningBatch(threshold); setMessage(`批次已创建：${result.id}，等待独立评估。`); data.reload(); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "批次创建失败，请重试。"); }
    finally { setBusy(false); }
  }
  if (!token) return null;
  const result = data.data;
  const status = result?.performance.status;
  return <><PageHeader eyebrow="Human Review Learning" title="人机共审学习状态" description="查看人工独立审核积累的样本和预测差异。统计只使用有效真实样本，每个维度单独计算分母。" icon={ShieldCheck} action={<Link className="button-secondary" href="/admin/field-review">进入逐条审核</Link>} />
    <main className="container-page space-y-6 py-8">
      <section className="panel space-y-2 p-5" aria-label="学习状态概览"><h2 className="font-semibold">当前状态：{!config.ready ? "加载中" : config.error ? "暂不可用" : !config.data?.enabled ? "未启用" : status === "ready_for_evaluation" ? "待评估" : "观察中"}</h2><p className="break-all text-sm">当前模型版本：{config.data?.model_version ?? "暂无"}</p><p className="text-sm">运行环境：{config.data?.actor_mode === "automation" ? "自动化实验（不计入真实人工样本）" : config.data?.actor_mode === "human" ? "人工审核" : "暂无"}</p><p className="text-sm">有效真实样本：{result?.performance.sample_count ?? "暂无"} · 最近 100 条一级准确率：{result?.performance.windows.recent_100 ? rate(result.performance.windows.recent_100.primary_accuracy, result.performance.windows.recent_100.primary_denominator) : "暂无"}</p><p className="text-xs text-muted">样本按已提交审核决定计数；同一候选的多次处理不是多份独立材料。缺失标注不计入相应分母。创建批次仅冻结评估材料，不执行训练或模型发布。</p><button className="button-secondary" onClick={() => { config.reload(); data.reload(); }}>刷新学习状态</button></section>
      {config.error || data.error || error ? <p role="alert" className="panel border-red-200 p-4 text-sm text-red-700">{config.error || data.error || error}</p> : null}
      {message ? <p role="status" className="text-sm text-emerald-800">{message}</p> : null}
      {config.data?.enabled && !result && !data.error ? <p role="status">正在加载学习记录…</p> : null}
      {result ? <>
        <div className="grid gap-4 xl:grid-cols-3">{([['all', '全部样本'], ['recent_50', '最近 50 条'], ['recent_100', '最近 100 条']] as const).map(([key, title]) => <MetricWindow key={key} title={title} value={result.performance.windows[key]} />)}</div>
        <section className="panel space-y-3 p-5" aria-label="模型版本对比"><h2 className="font-semibold">模型版本</h2>{Object.entries(result.performance.by_model_version).length ? Object.entries(result.performance.by_model_version).map(([version, group]) => <div key={version} className="rounded-lg border border-line p-3 text-sm"><p className="break-all">{version} · {group.sample_count} 条</p><p>一级准确率：{rate(group.windows.all.primary_accuracy, group.windows.all.primary_denominator)} · 政策精确率：{rate(group.windows.all.policy_precision, group.windows.all.policy_precision_denominator)} · 政策召回率：{rate(group.windows.all.policy_recall, group.windows.all.policy_recall_denominator)}</p></div>) : <p className="text-sm text-muted">暂无模型版本样本。</p>}</section>
        <section className="panel space-y-3 p-5" aria-label="学习批次"><h2 className="font-semibold">待评估批次</h2><div className="flex flex-wrap items-end gap-3"><label className="grid gap-1 text-sm">新批次样本门槛<select className="field" value={threshold} disabled={busy} onChange={(event) => setThreshold(Number(event.target.value) as 100 | 300 | 500)}>{[100, 300, 500].map(count => <option key={count} value={count}>{count} 条新有效样本</option>)}</select></label><button type="button" className="button-primary" disabled={busy} onClick={() => void createBatch()}>创建待评估批次</button></div>{result.batches.items.length ? <ul className="space-y-2 text-sm">{result.batches.items.map(batch => <li key={batch.id} className="break-all">{batch.id} · {batch.sample_count ?? "暂无"} 条 · {batch.status === "ready_for_evaluation" ? "待评估" : "观察中"}</li>)}</ul> : <p className="text-sm text-muted">暂无批次；达到门槛后可手动创建。</p>}</section>
        <section className="panel space-y-4 p-5" aria-label="已提交人工样本"><h2 className="font-semibold">已提交人工样本（{result.examples.total} 条）</h2><p className="text-xs text-muted">纠正会追加新版本并保留原记录，不修改已审核的业务事实。</p>{result.examples.items.map(example => <ExampleReview key={example.id} example={example} onSaved={data.reload} />)}<Pagination label="学习样本分页" page={examplePage} hasNext={(examplePage + 1) * 50 < result.examples.total} disabled={busy} onPage={setExamplePage} />{!result.examples.items.length ? <p className="text-sm text-muted">暂无真实人工样本。</p> : null}</section>
      </> : null}
    </main></>;
}
function MetricWindow({ title, value }: { title: string; value: LearningWindow }) {
  const rows = [["一级准确率", value.primary_accuracy, value.primary_denominator], ["二级准确率", value.secondary_accuracy, value.secondary_denominator], ["政策精确率", value.policy_precision, value.policy_precision_denominator], ["政策召回率", value.policy_recall, value.policy_recall_denominator], ["风险一致率", value.risk_agreement, value.risk_denominator], ["动作一致率", value.action_agreement, value.action_denominator], ["字段一致率", value.field_agreement, value.field_denominator]] as const;
  return <section className="panel space-y-3 p-4" aria-label={title + "指标"}><h2 className="font-semibold">{title} · {value.sample_count} 条</h2><table className="w-full text-left text-sm"><tbody>{rows.map(([label, metric, denominator]) => <tr key={label}><th className="py-2 font-normal">{label}</th><td>{rate(metric, denominator)}</td></tr>)}</tbody></table><h3 className="text-sm font-medium">已观察到的差异</h3>{Object.entries(value.error_types ?? {}).length ? <ul className="space-y-1 text-sm">{Object.entries(value.error_types).map(([kind, count]) => <li key={kind}>{errors[kind] ?? "其他判断差异"}：{count}</li>)}</ul> : <p className="text-sm text-muted">暂无记录。</p>}</section>;
}
function ExampleReview({ example, onSaved }: { example: LearningExample; onSaved: () => void }) {
  const [editing, setEditing] = useState(false); const [selected, setSelected] = useState(example.human_ground_truth.human_primary_type ?? "");
  const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function save() {
    if (!selected || !reason.trim() || busy) return;
    setBusy(true); setError("");
    try { await correctLearningExample(example.id, { human_primary_type: selected as PrimaryDocumentType }, reason.trim()); setEditing(false); onSaved(); }
    catch (exc) { setError(exc instanceof Error ? exc.message : "纠正未保存，请重试。"); }
    finally { setBusy(false); }
  }
  return <article className="space-y-2 rounded-lg border border-line p-4 text-sm"><p className="break-all">样本 {example.id} · 候选 #{example.candidate_id ?? "暂无"} · {example.superseded_by_example_id || example.learning_status === "superseded" ? "已被后续版本替代" : example.supersedes_example_id ? "纠正版本" : "当前有效版本"}</p><p>人工类型：{primaryLabel(example.human_ground_truth.human_primary_type)} · 提交后预测：{primaryLabel(example.shadow_prediction?.shadow_primary_type)}</p>{example.candidate_id ? <Link className="text-accent underline" href={`/admin/field-review?candidate=${example.candidate_id}`}>查看原审核材料</Link> : null}{example.supersedes_example_id ? <p>替代样本：{example.supersedes_example_id}</p> : null}{example.correction_reason ? <p>纠正原因：{example.correction_reason}</p> : null}
    {!example.superseded_by_example_id && example.learning_status !== "superseded" ? <button className="button-secondary ml-3" disabled={busy} onClick={() => setEditing(!editing)}>{editing ? "取消纠正" : "纠正人工类型"}</button> : null}
    {editing ? <div className="grid gap-3"><label className="grid gap-1">纠正后的人工一级类型<select className="field" disabled={busy} value={selected} onChange={(event) => setSelected(event.target.value as PrimaryDocumentType)}><option value="">请选择</option>{primaryDocumentTypes.map(item => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label className="grid gap-1">人工纠正原因<textarea className="field min-h-20 py-2" disabled={busy} value={reason} onChange={(event) => setReason(event.target.value)} /></label><button className="button-primary" disabled={busy || !selected || !reason.trim()} onClick={() => void save()}>追加纠正版本</button></div> : null}
    {error ? <p role="alert" className="text-red-700">{error}</p> : null}
  </article>;
}
