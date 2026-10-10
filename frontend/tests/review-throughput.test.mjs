import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium, mount } from "./browser-harness.mjs";
let browser;
before(async () => { browser = await chromium.launch({ headless: true, channel: "msedge" }); });
after(async () => { await browser?.close(); });
const entry = "src/app/admin/field-review/page.tsx";
const source = (title = "全国公告", date = "2026-09-01", verified = true) => ({ source_type: "organizer_notice", source_title: title, source_url: "https://example.test/notice", publisher: "赛事组委会", published_at: date, collected_at: "2026-09-28T00:00:00Z", verification_state: verified ? "VERIFIED" : "UNVERIFIED", verified_at: verified ? "2026-09-28T01:00:00Z" : null, verified_by: verified ? 9 : null });
const row = (id, risk = "LOW_RISK") => ({ id, title: "材料 "+id, description: "原始材料", entity_type: "competition", competition_id: id, competition_name: "赛事 "+id, university_id: null, origin: "crawler", status: "pending", created_at: "2026-09-28T00:00:00Z", preview_token: "v-"+id, risk_level: risk, risk_reasons: risk === "HIGH_RISK" ? ["CONFLICT"] : [], low_risk_fields: risk === "LOW_RISK" ? ["description"] : [], bulk_eligible_fields: risk === "LOW_RISK" ? ["description"] : [], flags: [risk], history: [], fields: [{ field_name: "description", display_name: "赛事介绍", current_value: null, candidate_value: "介绍 "+id, changed: true, change_type: "add", verification_state: "VERIFIED", decision: "pending", proposals: [{ id: "p-"+id, candidate_value: "介绍 "+id, source: source() }], conflicts: [], timeline: [], risk_reasons: [] }] });
const config = { fields: { competition: [{ field_name: "description", display_name: "赛事介绍", value_type: "string" }], edition: [] }, source_types: [{ value: "organizer_notice", label: "主办方通知", priority: 1 }] };
const group = { completed_samples: 0, active_sessions: 0, interrupted_sessions: 0, mean_seconds: null, median_seconds: null, p90_seconds: null, theoretical_per_hour: null };
const stats = { counts: { pending: 21, approved: 0, rejected: 0, partially_approved: 0, conflict: 1, no_source: 0, duplicate_suspected: 0, low_risk: 20, high_risk: 1, school_relations: 0 }, telemetry: { groups: { human: group, automation: group } } };
function respond(rows) {
  return (url, request) => {
    if (url.pathname.endsWith("/config")) return config;
    if (url.pathname.endsWith("/statistics")) return stats;
    if (url.pathname.endsWith("/timing/start")) return { session_id: "session-1", mode: request.postDataJSON().mode, status: "active", candidate_id: Number(url.pathname.split("/").at(-3)), phase_seconds: {} };
    if (url.pathname.endsWith("/timing/event")) return { session_id: "session-1", status: "active" };
    if (url.pathname.endsWith("/field-reviews")) { const offset = Number(url.searchParams.get("offset")); return { items: rows.slice(offset, offset + 20), total: rows.length }; }
    return { data: rows.find((item) => url.pathname.endsWith("/"+item.id)) ?? {} };
  };
}
// Catches page-local selection and reset-on-error losing the reviewer's work.
test("cross-page low-risk batch preserves selection, note, filters and page on atomic failure", async () => {
  const rows = Array.from({ length: 21 }, (_, i) => row(i + 101)); rows[1] = row(102, "HIGH_RISK");
  const requests = []; const base = respond(rows); let fail = true;
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    requests.push({ url, body: request.postDataJSON() });
    if (url.pathname.endsWith("/bulk-preview")) return { items: request.postDataJSON().items.map((item) => rows.find((r) => r.id === item.id)), total: 2, field_count: 2, transaction: "atomic" };
    if (url.pathname.endsWith("/bulk-review")) return fail ? { status: 409, message: "候选 #121 已改变；整批0条成功" } : { items: [], total: 2, succeeded: 2, failed: 0, pending_ids: [], transaction: "atomic" };
    return base(url, request);
  });
  await page.getByLabel("搜索候选").fill("赛事");
  await page.getByLabel("风险筛选").selectOption("LOW_RISK");
  await page.getByLabel("关系类型筛选").selectOption("registration_notice");
  await page.getByLabel("队列排序").selectOption("oldest");
  await page.getByRole("button", { name: "应用筛选" }).click();
  await page.getByLabel("选择候选 101").check();
  assert.equal(await page.getByLabel("选择候选 102").isDisabled(), true);
  await page.getByRole("button", { name: "下一页" }).click();
  await page.getByLabel("选择候选 121").check();
  const batch = page.getByRole("region", { name: "跨页批量审核" });
  await batch.getByText("已选择 2 / 50 条候选", { exact: true }).waitFor();
  await batch.getByText("赛事 101", { exact: true }).waitFor();
  await batch.getByText("赛事 121", { exact: true }).waitFor();
  await page.getByLabel("批量审核意见").fill("逐项核对来源后补全");
  await page.getByRole("button", { name: "预览批量批准" }).click();
  await batch.getByText("来源：主办方通知 · 全国公告 · 赛事组委会 · 已核验", { exact: true }).first().waitFor();
  await page.getByLabel("已核对整批摘要，确认原子提交").check();
  await page.getByRole("button", { name: "确认原子批准" }).click();
  await page.getByRole("alert").getByText("候选 #121 已改变；整批0条成功", { exact: false }).waitFor();
  assert.equal(await page.getByLabel("批量审核意见").inputValue(), "逐项核对来源后补全");
  assert.equal(await page.getByLabel("选择候选 121").isChecked(), true);
  assert.equal(await page.getByLabel("搜索候选").inputValue(), "赛事");
  assert.equal(await page.getByLabel("风险筛选").inputValue(), "LOW_RISK");
  const query = requests.filter((r) => r.url.pathname.endsWith("/field-reviews")).at(-1).url.searchParams;
  assert.equal(query.get("offset"), "20"); assert.equal(query.get("search"), "赛事"); assert.equal(query.get("relation_type"), "registration_notice"); assert.equal(query.get("sort"), "oldest");
  const payload = requests.find((r) => r.url.pathname.endsWith("/bulk-review")).body;
  assert.deepEqual(payload.items.map((x) => x.id), [101, 121]);
  assert.deepEqual(payload.items.map((x) => x.field_names), [["description"], ["description"]]);
  fail = false;
  await page.getByRole("button", { name: "预览批量批准" }).click();
  await page.getByLabel("已核对整批摘要，确认原子提交").check();
  await page.getByRole("button", { name: "确认原子批准" }).click();
  await page.getByText("整批 2 条候选已批准。", { exact: true }).waitFor();
  await batch.getByText("已选择 0 / 50 条候选", { exact: true }).waitFor();
  await page.close();
});
// Catches hiding outside sources or choosing a winner based on date alone.
test("source timeline orders dated evidence before unknown dates and displays complete values", async () => {
  const item = row(101, "HIGH_RISK");
  item.fields[0].timeline = [
    { candidate_id: 102, proposal_id: "new", candidate_value: "延期至十一月", source: { ...source("延期更正公告", "2026-10-02"), access_status: "readable" }, scope: "competition", announcement_hint: "延期或更正" },
    { candidate_id: 103, proposal_id: "unknown", candidate_value: "未明确日期的不同意见", source: { ...source("无日期材料", null), source_failure_reason: "timeout" }, scope: "competition", announcement_hint: null },
    { candidate_id: 101, proposal_id: "old", candidate_value: "最初十月截止", source: source("初始公告", "2026-09-01"), scope: "competition", announcement_hint: null },
  ];
  const page = await mount(browser, entry, "default", {}, respond([item]));
  await page.getByRole("button", { name: "查看候选 材料 101" }).click();
  const timeline = page.getByRole("region", { name: "赛事介绍来源时间线" });
  await timeline.getByText("未明确日期的不同意见", { exact: true }).waitFor();
  const content = await timeline.innerText();
  assert.ok(content.indexOf("最初十月截止") < content.indexOf("延期至十一月"));
  assert.ok(content.indexOf("延期至十一月") < content.indexOf("未明确日期的不同意见"));
  assert.ok(content.includes("赛事组委会") && content.includes("采集时间") && content.includes("timeout"));
  assert.equal(await timeline.getByRole("link", { name: /打开来源原文/ }).count(), 3);
  assert.equal(await page.getByLabel("采用赛事介绍候选 1").isChecked(), false);
  await page.close();
});

function schoolRow(kind = "policy") {
  const item = row(201, "HIGH_RISK"); item.fields = []; item.bulk_eligible_fields = []; item.low_risk_fields = [];
  item.collection_context = { kind: "school_mapping", school_name: "示例大学", source_quality: "B", notice_type: kind === "policy" ? "policy_recognition" : "registration_notice", is_formal_recognition: kind === "policy" };
  item.relation = { candidate_id: 201, preview_token: "relation-v1", status: "pending", relation_kind: kind, university_id: 8, school_name: "示例大学", competition_id: 201, competition_name: "赛事 201", notice_type: item.collection_context.notice_type, year: kind === "notice" ? 2026 : null, edition_id: null, source: source("学校正式文件", "2025-01-01", false), prepared: {}, flags: [], blocking_reasons: ["需要准备范围并核验来源"], can_approve: false, existing_records: [], history: [], decision: null };
  return item;
}
// Catches upgrading historical graduate policy to current all-undergraduate recognition.
test("school policy has independent preparation, verification and review while failure retains form", async () => {
  const item = schoolRow(); const writes = []; const base = respond([item]);
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/relation/prepare")) {
      const body = request.postDataJSON(); writes.push({ path: "prepare", body });
      item.relation = { ...item.relation, prepared: body, preview_token: "relation-v2", blocking_reasons: ["来源待核验"] }; return { data: item.relation };
    }
    if (url.pathname.endsWith("/relation/verify-source")) {
      writes.push({ path: "verify", body: request.postDataJSON() });
      item.relation = { ...item.relation, source: source("学校正式文件"), preview_token: "relation-v3", blocking_reasons: [], can_approve: true }; return { data: item.relation };
    }
    if (url.pathname.endsWith("/relation/review")) { writes.push({ path: "review", body: request.postDataJSON() }); return { status: 409, message: "关系预览已改变，请重核" }; }
    return base(url, request);
  });
  await page.getByRole("button", { name: "查看候选 材料 201" }).click();
  const relation = page.getByRole("region", { name: "学校关系审核" });
  await relation.getByLabel("政策范围").selectOption("university");
  await relation.getByLabel("适用学生").selectOption("graduate");
  await relation.getByLabel("适用范围说明").fill("仅限本校研究生");
  await relation.getByLabel("有效期说明").fill("2025历史文件，当前效力尚未确认");
  await relation.getByLabel("赛事认定条款").fill("附件第八项明确列示赛事201");
  await relation.getByLabel("关系审核意见").fill("只保留研究生历史适用范围");
  assert.equal(await relation.getByLabel("确认当前仍然有效").isChecked(), false);
  await relation.getByRole("button", { name: "保存关系准备" }).click();
  await relation.getByLabel("关系审核意见").fill("核对原文件与赛事具体条款");
  await relation.getByRole("button", { name: "已核对学校原始来源" }).click();
  await relation.getByLabel("关系处理方式").selectOption("approve");
  await relation.getByLabel("适用学生").selectOption("all");
  assert.equal(await relation.getByRole("button", { name: "提交学校关系审核" }).isDisabled(), true);
  await relation.getByLabel("适用学生").selectOption("graduate");
  await relation.getByLabel("关系审核意见").fill("仅批准历史研究生范围");
  await relation.getByRole("button", { name: "提交学校关系审核" }).click();
  await relation.getByRole("alert").getByText("关系预览已改变，请重核").waitFor();
  assert.equal(await relation.getByLabel("关系审核意见").inputValue(), "仅批准历史研究生范围");
  assert.equal(await relation.getByLabel("关系处理方式").inputValue(), "approve");
  assert.equal(await relation.getByLabel("适用学生").inputValue(), "graduate");
  assert.equal(writes[0].body.current_validity_confirmed, false);
  assert.equal(writes[0].body.student_scope, "graduate");
  assert.equal(writes[0].body.notice_type, undefined);
  assert.equal(writes[0].body.year, undefined);
  assert.equal(writes[1].body.preview_token, "relation-v2");
  assert.deepEqual(writes[2].body, { preview_token: "relation-v3", note: "仅批准历史研究生范围", action: "approve" });
  await page.close();
});
// Catches treating a school registration notice as a policy, and blocking safe reject/defer.
test("school notice conflict cannot approve or change material type and may defer", async () => {
  const item = schoolRow("notice"); item.relation.flags = ["RELATION_CONFLICT"]; item.relation.blocking_reasons = ["原始材料已撤销"];
  const writes = []; const base = respond([item]);
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/relation/review")) { writes.push(request.postDataJSON()); return { data: { ...item.relation, decision: { action: "defer" } } }; }
    return base(url, request);
  });
  await page.getByRole("button", { name: "查看候选 材料 201" }).click();
  const relation = page.getByRole("region", { name: "学校关系审核" });
  assert.equal(await relation.getByLabel("政策范围").count(), 0);
  assert.equal(await relation.getByLabel("关系类型").count(), 0);
  await relation.getByLabel("关系处理方式").selectOption("approve");
  await relation.getByLabel("关系审核意见").fill("先保留撤销线索");
  assert.equal(await relation.getByRole("button", { name: "提交学校关系审核" }).isDisabled(), true);
  await relation.getByLabel("关系处理方式").selectOption("defer");
  await relation.getByRole("button", { name: "提交学校关系审核" }).click();
  await page.getByText("学校关系已暂缓，仍待处理。", { exact: true }).waitFor();
  assert.equal(writes[0].action, "defer");
  await page.close();
});
// Catches human/automation mixing and missing actual user-action timing events.
test("explicit automation timing records source, decision and submit separately from human statistics", async () => {
  const item = row(101); const calls = []; const base = respond([item]);
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.includes("/timing/")) { calls.push({ path: url.pathname, body: request.postDataJSON() }); return { data: { session_id: "session-1", candidate_id: 101, candidate_ids: [101], sample_type: "single", mode: "automation", status: "active", phase_seconds: {} } }; }
    if (url.pathname.endsWith("/review")) return { data: { ...item, status: "approved" } };
    return base(url, request);
  });
  await page.getByLabel("计时模式").selectOption("automation");
  await page.getByRole("button", { name: "查看候选 材料 101" }).click();
  await page.getByRole("button", { name: "开始本条计时" }).click();
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  await page.getByRole("link", { name: /打开来源原文/ }).first().click();
  await page.getByLabel("采用赛事介绍候选 1").check();
  await page.getByLabel("赛事介绍的处理方式").selectOption("approve");
  await page.getByLabel("审核意见", { exact: true }).fill("自动化隔离数据实验");
  await page.getByRole("button", { name: "提交字段审核", exact: true }).click();
  await page.getByText("字段审核已保存；未选择的字段继续待处理。", { exact: true }).waitFor();
  assert.equal(calls[0].body.mode, "automation");
  assert.deepEqual(calls.filter((call) => call.body.event).map((call) => call.body.event), ["source_open", "decision", "submit"]);
  assert.ok(calls.filter((call) => call.body.event).every((call) => call.body.session_id === "session-1"));
  const panel = page.getByRole("region", { name: "审核统计" });
  assert.ok((await panel.innerText()).includes("人工") && (await panel.innerText()).includes("自动化"));
  await page.close();
});

test("selection is capped at 50 and batch timing starts one wall-clock session", async () => {
  const rows = Array.from({ length: 51 }, (_, i) => row(i + 101)); const starts = []; const base = respond(rows);
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/timing/start")) { const body = request.postDataJSON(); starts.push(body); return { data: { session_id: "batch-session", candidate_id: 101, candidate_ids: body.candidate_ids, sample_type: "batch", mode: body.mode, status: "active" } }; }
    return base(url, request);
  });
  await page.getByLabel("计时模式").selectOption("automation");
  for (let id = 101; id <= 150; id++) { if (id === 121 || id === 141) await page.getByRole("button", { name: "下一页" }).click(); await page.getByLabel("选择候选 " + id).check(); }
  assert.equal(await page.getByLabel("选择候选 151").isDisabled(), true);
  await page.getByText("已选择 50 / 50 条候选", { exact: true }).waitFor();
  await page.getByRole("button", { name: "开始整批计时" }).click();
  await page.getByText("自动化计时进行中", { exact: false }).waitFor();
  assert.equal(starts.length, 1); assert.equal(starts[0].mode, "automation"); assert.deepEqual(starts[0].candidate_ids, Array.from({ length: 50 }, (_, i) => i + 101));
  await page.close();
});

test("large source timelines fetch additional evidence in pages", async () => {
  const item = row(101); item.fields[0].timeline_total = 2;
  item.fields[0].timeline = [{ candidate_id: 101, proposal_id: "first", candidate_value: "首份证据", source: source() }];
  const calls = []; const base = respond([item]);
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/sources")) { calls.push(url); return { items: [{ field_name: "description", candidate_id: 102, proposal_id: "second", candidate_value: "追加分页证据", source: source("追加原文", "2026-09-02") }], total: 2 }; }
    return base(url, request);
  });
  await page.getByRole("button", { name: "查看候选 材料 101" }).click();
  const timeline = page.getByRole("region", { name: "赛事介绍来源时间线" });
  await timeline.getByRole("button", { name: "查看更多来源" }).click({ timeout: 5000 });
  await timeline.getByText("追加分页证据", { exact: true }).waitFor();
  assert.equal(calls[0].searchParams.get("field_name"), "description"); assert.equal(calls[0].searchParams.get("offset"), "1"); assert.equal(calls[0].searchParams.get("limit"), "20");
  assert.equal(await timeline.getByRole("button", { name: "查看更多来源" }).count(), 0);
  await page.close();
});
test("school source normal and middle clicks each record one source-open event", async () => {
  const item = schoolRow("notice"); const calls = []; const base = respond([item]);
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.includes("/timing/")) { calls.push(request.postDataJSON()); return { data: { session_id: "school-clock", candidate_id: 201, candidate_ids: [201], mode: "automation", status: "active" } }; }
    if (url.pathname.endsWith("/relation/review")) return { data: { ...item.relation, status: "deferred", decision: { action: "defer" } } };
    return base(url, request);
  });
  await page.getByLabel("计时模式").selectOption("automation");
  await page.getByRole("button", { name: "查看候选 材料 201" }).click();
  await page.getByRole("button", { name: "开始本条计时" }).click();
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  const link = page.getByRole("link", { name: "打开学校来源原文" });
  await link.click(); await link.click({ button: "middle" });
  await page.getByLabel("关系处理方式").selectOption("defer");
  await page.getByLabel("关系审核意见").fill("原文已打开，继续等待必要资料");
  await page.getByRole("button", { name: "提交学校关系审核" }).click();
  await page.getByText("学校关系已暂缓，仍待处理。", { exact: true }).waitFor();
  assert.deepEqual(calls.filter((call) => call.event).map((call) => call.event), ["source_open", "source_open", "decision", "submit"]);
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  await page.close();
});

test("partial field decisions stay timed until all fields are terminal even for mixed outcomes", async () => {
  const item = row(101, "HIGH_RISK");
  item.fields.push({ ...item.fields[0], field_name: "frequency", display_name: "举办频率", decision: "pending", proposals: [{ id: "frequency-1", candidate_value: "每年", source: source() }] });
  const base = respond([item]); let submitted = 0;
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.includes("/timing/")) return { data: { session_id: "multi-clock", candidate_id: 101, candidate_ids: [101], mode: "automation", status: "active" } };
    if (url.pathname.endsWith("/review")) { submitted++; item.status = "partially_approved"; item.preview_token = "partial-" + submitted; item.fields[0].decision = "approved"; if (submitted === 2) item.fields[1].decision = "rejected"; return { data: item }; }
    return base(url, request);
  });
  await page.getByLabel("计时模式").selectOption("automation");
  await page.getByRole("button", { name: "查看候选 材料 101" }).click();
  await page.getByRole("button", { name: "开始本条计时" }).click();
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  await page.getByLabel("采用赛事介绍候选 1").check();
  await page.getByLabel("赛事介绍的处理方式").selectOption("approve");
  await page.getByLabel("审核意见", { exact: true }).fill("先批准介绍");
  await page.getByRole("button", { name: "提交字段审核", exact: true }).click();
  await page.getByText("字段审核已保存；未选择的字段继续待处理。", { exact: true }).waitFor();
  await page.getByRole("article", { name: "候选详情" }).getByText("已批准", { exact: true }).waitFor();
  await page.getByLabel("审核意见", { exact: true }).fill("剩余频率证据不足，拒绝");
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  await page.getByLabel("举办频率的处理方式").selectOption("reject");
  await page.getByRole("button", { name: "提交字段审核", exact: true }).click();
  await page.getByText("本次计时已完成", { exact: true }).waitFor();
  assert.equal(submitted, 2);
  await page.close();
});

test("batch success does not finish timing when returned candidates still have pending fields", async () => {
  const item = row(101); const base = respond([item]);
  item.fields.push({ ...item.fields[0], field_name: "frequency", display_name: "举办频率", decision: "pending" });
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.includes("/timing/")) return { data: { session_id: "partial-batch", candidate_id: 101, candidate_ids: [101], mode: "automation", status: "active" } };
    if (url.pathname.endsWith("/bulk-preview")) return { items: [item], total: 1, field_count: 1, transaction: "atomic" };
    if (url.pathname.endsWith("/bulk-review")) return { items: [{ ...item, status: "partially_approved", fields: item.fields.map((field, index) => ({ ...field, decision: index === 0 ? "approved" : "pending" })) }], total: 1, succeeded: 1, failed: 0, pending_ids: [], transaction: "atomic" };
    return base(url, request);
  });
  await page.getByLabel("计时模式").selectOption("automation");
  await page.getByLabel("选择候选 101").check();
  await page.getByRole("button", { name: "开始整批计时" }).click();
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  await page.getByLabel("批量审核意见").fill("只批准有证据的字段");
  await page.getByRole("button", { name: "预览批量批准" }).click();
  await page.getByLabel("已核对整批摘要，确认原子提交").check();
  await page.getByRole("button", { name: "确认原子批准" }).click();
  await page.getByText("整批 1 条候选的选定字段已批准，其他字段仍待处理。", { exact: true }).waitFor();
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  await page.close();
});
test("active timing locks its mode and an expired session can be explicitly restarted", async () => {
  const item = row(101); const starts = []; const base = respond([item]);
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/timing/start")) { starts.push(request.postDataJSON()); return { data: { session_id: "clock-" + starts.length, candidate_id: 101, candidate_ids: [101], mode: request.postDataJSON().mode, status: "active" } }; }
    if (url.pathname.endsWith("/timing/event")) return { status: 409, message: "Timing session is no longer active" };
    return base(url, request);
  });
  await page.getByLabel("计时模式").selectOption("automation");
  await page.getByRole("button", { name: "查看候选 材料 101" }).click();
  await page.getByRole("button", { name: "开始本条计时" }).click();
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  const locked = await page.getByLabel("计时模式").isDisabled();
  await page.getByRole("link", { name: /打开来源原文/ }).first().click();
  await page.getByRole("alert").getByText("Timing session is no longer active", { exact: false }).waitFor();
  assert.equal(await page.getByRole("button", { name: "开始本条计时" }).count(), 1);
  await page.getByRole("button", { name: "开始本条计时" }).click();
  await page.getByText("自动化计时进行中", { exact: true }).waitFor();
  assert.equal(locked, true); assert.equal(starts.length, 2); assert.ok(starts.every((start) => start.mode === "automation"));
  await page.close();
});