import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium, mount } from "./browser-harness.mjs";
let browser;
before(async () => { browser = await chromium.launch({ headless: true, channel: "msedge" }); });
after(async () => { await browser?.close(); });
const entry = "src/app/admin/field-review/page.tsx";
const config = { fields: { competition: [], edition: [] }, source_types: [] };
const makeRow = (id = 11) => ({ id, title: `盲审材料 ${id}`, description: "来源原文事实", entity_type: "competition", status: "pending", preview_token: `p-${id}`, fields: [], flags: [], history: [], bulk_eligible_fields: [], origin_source_url: "https://example.test/source", document_classification: { primary_type: "policy", document_type: "award_policy_document", confidence: 0.99, classification_reason: "不应泄露的预测理由", policy_assessment: { is_policy: true, policy_status: "POLICY" } } });
function responder({ enabled = true, failComplete = false, failBusiness = false } = {}) {
  let row = makeRow(); const writes = [];
  return { writes, respond(url, request) {
    const body = request.postDataJSON(); const path = url.pathname;
    if (request.method() !== "GET") writes.push({ path, body, learningSession: request.headers()["x-review-learning-session"] });
    if (path.endsWith("review-learning/config")) return { enabled, actor_mode: "human", model_version: "shadow-v1-test" };
    if (path.endsWith("review-learning/sessions")) return { session_id: `s-${body.candidate_id}`, candidate_id: body.candidate_id, state: "active", started_at: "2026-10-07T00:00:00Z" };
    if (path.endsWith("/events")) return { state: "active" };
    if (path.endsWith("/complete")) { if (failComplete) { failComplete = false; return { status: 503, message: "学习库暂不可用" }; } return { id: "example-1", human_ground_truth: body }; }
    if (path.endsWith("/reject-unstructured")) { if (failBusiness) return { status: 409, message: "业务预览过期" }; row = { ...row, status: "rejected", preview_token: "done" }; return { data: row }; }
    if (path.endsWith("/config")) return config;
    if (path.endsWith("/field-reviews")) return { items: [row, makeRow(12)], total: 2 };
    if (path.endsWith("/field-reviews/11")) return { data: row };
    if (path.endsWith("/field-reviews/12")) return { data: makeRow(12) };
    return {};
  } };
}
// Removing blind mode or preselecting machine labels must fail this test.
test("enabled learning starts on candidate opening, hides predictions and requires empty human primary", async () => {
  const stub = responder(); const page = await mount(browser, entry, "default", {}, stub.respond);
  await page.getByRole("button", { name: "查看候选 盲审材料 11" }).click();
  const primary = page.getByLabel("人工一级类型"); await primary.waitFor();
  assert.equal(await primary.inputValue(), "");
  assert.deepEqual(await primary.locator("option").allTextContents(), ["请选择", "参赛相关", "结果/公示", "赛事信息", "政策/认定", "更新/更正", "转发", "其他"]);
  assert.equal(await page.getByRole("region", { name: "系统文档分类" }).count(), 0);
  assert.doesNotMatch(await page.locator("body").innerText(), /不应泄露的预测理由/);
  await page.getByLabel("拒绝说明").fill("原文与赛事无关");
  assert.equal(await page.getByRole("button", { name: "拒绝此原始材料" }).isDisabled(), true);
  await primary.selectOption("other");
  await page.getByRole("button", { name: "拒绝此原始材料" }).click();
  await page.getByText("学习样本已保存", { exact: false }).waitFor();
  assert.deepEqual(stub.writes.filter(x => x.path.endsWith("/sessions")).map(x => x.body), [{ candidate_id: 11 }]);
  const completed = stub.writes.findIndex(x => x.path.endsWith("/complete"));
  assert.ok(completed > stub.writes.findIndex(x => x.path.endsWith("/reject-unstructured")));
  assert.deepEqual(stub.writes[completed].body, { human_primary_type: "other" });
  assert.equal(stub.writes.find(x => x.path.endsWith("/reject-unstructured")).learningSession, "s-11");
  assert.ok(stub.writes.some(x => x.body?.event === "submit"));
  assert.ok(stub.writes.some(x => x.body?.event === "decision"));
  assert.equal(await page.getByLabel("选择候选 11").isDisabled(), true);
  assert.deepEqual(await page.evaluate(() => window.testRoutes), []);
  await page.close();
});
// The retry must never call the already-successful business write again.
test("learning failure after business success exposes learning-only retry", async () => {
  const stub = responder({ failComplete: true }); const page = await mount(browser, entry, "default", {}, stub.respond);
  await page.getByRole("button", { name: "查看候选 盲审材料 11" }).click();
  await page.getByLabel("人工一级类型").selectOption("other");
  await page.getByLabel("拒绝说明").fill("人工核对后拒绝");
  await page.getByRole("button", { name: "拒绝此原始材料" }).click();
  await page.getByText("业务审核已保存", { exact: false }).waitFor();
  await page.getByRole("button", { name: "仅重试保存学习样本" }).click();
  await page.getByText("学习样本已保存", { exact: false }).waitFor();
  assert.equal(stub.writes.filter(x => x.path.endsWith("/reject-unstructured")).length, 1);
  assert.equal(stub.writes.filter(x => x.path.endsWith("/complete")).length, 2);
  await page.close();
});
// Failure and identity/candidate changes must not produce or transfer labels.
test("failed business write produces no sample and candidate labels remain isolated", async () => {
  const stub = responder({ failBusiness: true }); const page = await mount(browser, entry, "default", {}, stub.respond);
  await page.getByRole("button", { name: "查看候选 盲审材料 11" }).click();
  await page.getByLabel("人工一级类型").selectOption("result");
  await page.getByLabel("拒绝说明").fill("核验说明");
  await page.getByRole("button", { name: "拒绝此原始材料" }).click();
  await page.getByText("业务预览过期", { exact: false }).waitFor();
  assert.equal(stub.writes.filter(x => x.path.endsWith("/complete")).length, 0);
  await page.getByRole("button", { name: "查看候选 盲审材料 12" }).click();
  assert.equal(await page.getByLabel("人工一级类型").inputValue(), "");
  await page.getByRole("button", { name: "查看候选 盲审材料 11" }).click();
  await page.waitForFunction(() => document.querySelector('[aria-label="人工一级类型"]')?.value === "result");
  await page.evaluate(() => window.changeSession(null));
  await page.waitForFunction(() => !document.body.textContent.includes("人工一级类型"));
  await page.close();
});
test("disabled learning preserves ordinary review without session writes", async () => {
  const stub = responder({ enabled: false }); const page = await mount(browser, entry, "default", {}, stub.respond);
  await page.getByRole("button", { name: "查看候选 盲审材料 11" }).click();
  await page.getByRole("region", { name: "系统文档分类" }).waitFor();
  assert.equal(await page.getByLabel("人工一级类型").count(), 0);
  assert.equal(stub.writes.length, 0);
  await page.close();
});


// Null metrics must stay undefined, with the actual dimension denominator; batch creation is explicit.
test("learning status shows exact metric denominators and creates only the selected batch threshold", async () => {
  const writes = [];
  const window = { sample_count: 3, primary_accuracy: 2/3, primary_denominator: 3, secondary_accuracy: null, secondary_denominator: 0, policy_precision: null, policy_precision_denominator: 0, policy_recall: 0.5, policy_recall_denominator: 2, risk_agreement: null, risk_denominator: 0, action_agreement: 1, action_denominator: 3, field_agreement: null, field_denominator: 0, error_types: { POLICY_FALSE_POSITIVE: 1 }, model_versions: ["shadow-v1-test"] };
  const page = await mount(browser, "src/app/admin/review-learning/page.tsx", "default", {}, (url, request) => {
    if (request.method() !== "GET") { writes.push({ path: url.pathname, body: request.postDataJSON() }); return { data: { id: "b1", sample_count: 300, status: "ready_for_evaluation" } }; }
    if (url.pathname.endsWith("/config")) return { enabled: true, actor_mode: "human", model_version: "shadow-v1-test" };
    if (url.pathname.endsWith("/performance")) return { sample_count: 3, windows: { all: window, recent_50: window, recent_100: window }, by_model_version: { "shadow-v1-test": { sample_count: 3, windows: { all: window, recent_50: window, recent_100: window } } } };
    return { items: [], total: 0 };
  });
  await page.getByRole("heading", { name: "人机共审学习状态" }).waitFor();
  const all = page.getByRole("region", { name: "全部样本指标" });
  await all.getByText("66.7% · 分母 3", { exact: true }).waitFor();
  await all.getByText("政策误判：1", { exact: true }).waitFor();
  await all.getByRole("row", { name: /政策精确率/ }).getByText("暂无 · 分母 0", { exact: true }).waitFor();
  assert.equal(writes.length, 0);
  await page.getByLabel("新批次样本门槛").selectOption("300");
  await page.getByRole("button", { name: "创建待评估批次" }).click();
  await page.getByText("批次已创建", { exact: false }).waitFor();
  assert.deepEqual(writes, [{ path: "/api/admin/review-learning/batches", body: { min_samples: 300 } }]);
  assert.doesNotMatch(await page.locator("body").innerText(), /已训练|已部署/);
  await page.close();
});
// A source verification changes the business preview but must retain the original blind session and labels.
test("source verification reload retains independent labels and records source opens", async () => {
  let row = makeRow(); const writes = [];
  row.fields = [{ field_name: "description", display_name: "赛事介绍", current_value: "旧介绍", candidate_value: "新介绍", change_type: "modify", decision: "pending", proposals: [{ id: "p1", candidate_value: "新介绍", confidence: 0.95, source: { source_type: "organizer_notice", source_url: "https://example.test/source", source_title: "原始公告", publisher: "主办方", verification_state: "UNVERIFIED" } }] }];
  const base = responder();
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (request.method() !== "GET") writes.push({ path: url.pathname, body: request.postDataJSON(), learningSession: request.headers()["x-review-learning-session"] });
    if (url.pathname.endsWith("/review")) { row = { ...row, status: "rejected", fields: row.fields.map(field => ({ ...field, decision: "rejected" })) }; return { data: row }; }
    if (url.pathname.endsWith("/verify")) { row = { ...row, preview_token: "verified-p2" }; return { data: row }; }
    if (url.pathname.endsWith("/field-reviews/11")) return { data: row };
    if (url.pathname.endsWith("/field-reviews")) return { items: [row], total: 1 };
    return base.respond(url, request);
  });
  await page.getByRole("button", { name: "查看候选 原始公告" }).click();
  await page.getByLabel("人工一级类型").selectOption("information");
  await page.getByRole("link", { name: "查看提交时的原始来源（尚未核验）" }).evaluate(link => { link.addEventListener('click', event => event.preventDefault(), { once: true }); link.click(); });
  await page.getByLabel("审核意见", { exact: true }).fill("已阅读原公告");
  await page.getByRole("button", { name: "核验来源 p1" }).click();
  await page.getByText("来源核验已保存", { exact: false }).waitFor();
  assert.equal(await page.getByLabel("人工一级类型").inputValue(), "information");
  assert.equal(writes.filter(x => x.path.endsWith("/sessions")).length, 1);
  assert.ok(writes.some(x => x.body?.event === "source_open"));
  assert.equal(writes.filter(x => x.path.endsWith("/complete")).length, 0);
  assert.doesNotMatch(await page.locator("body").innerText(), /95%|不应泄露的预测理由/);
  await page.getByLabel("赛事介绍的处理方式").selectOption("reject");
  await page.getByLabel("审核意见", { exact: true }).fill("内容与核验材料不符");
  await page.getByRole("button", { name: "提交字段审核", exact: true }).click();
  await page.getByText("学习样本已保存", { exact: false }).waitFor();
  assert.equal(writes.find(x => x.path.endsWith("/review")).learningSession, "s-11");
  await page.close();
});
// Relation review must also require an independent primary and only capture after the committed review.
test("school relation review shares blind labels and keeps explicit relation decision separate", async () => {
  const writes = []; const base = responder(); let row = makeRow();
  row.collection_context = { kind: "school_mapping", school_name: "示例学校", notice_type: "registration_notice", source_quality: "B" };
  row.relation = { candidate_id: 11, status: "pending", preview_token: "rel-1", relation_kind: "notice", university_id: 2, competition_id: 3, notice_type: "registration_notice", year: 2026, prepared: {}, source: { source_url: "https://example.test/school", source_title: "学校公告", publisher: "学校", verification_state: "UNVERIFIED" }, flags: [], blocking_reasons: [], can_approve: false, existing_records: [], history: [] };
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (request.method() !== "GET") writes.push({ path: url.pathname, body: request.postDataJSON(), learningSession: request.headers()["x-review-learning-session"] });
    if (url.pathname.endsWith("/relation/review")) { row = { ...row, status: "rejected", relation: { ...row.relation, status: "rejected" } }; return { data: row.relation }; }
    if (url.pathname.endsWith("/field-reviews/11")) return { data: row };
    if (url.pathname.endsWith("/field-reviews")) return { items: [row], total: 1 };
    return base.respond(url, request);
  });
  await page.getByRole("button", { name: "查看候选 学校公告" }).click();
  await page.getByLabel("关系审核意见").fill("学校材料不适用于此届次");
  await page.getByLabel("关系处理方式").selectOption("reject");
  assert.equal(await page.getByRole("button", { name: "提交学校关系审核" }).isDisabled(), true);
  assert.equal(await page.getByRole("region", { name: "系统文档分类" }).count(), 0);
  await page.getByLabel("人工一级类型").selectOption("participation");
  await page.getByRole("button", { name: "提交学校关系审核" }).click();
  await page.getByText("学习样本已保存", { exact: false }).waitFor();
  assert.deepEqual(writes.find(x => x.path.endsWith("/complete")).body, { human_primary_type: "participation" });
  assert.deepEqual(writes.find(x => x.body?.event === "submit").body.details, { human_primary_type: "participation" });
  assert.ok(writes.findIndex(x => x.path.endsWith("/complete")) > writes.findIndex(x => x.path.endsWith("/relation/review")));
  assert.equal(await page.getByRole("button", { name: "开始下一次独立审核" }).count(), 0);
  assert.equal(writes.find(x => x.path.endsWith("/relation/review")).learningSession, "s-11");
  await page.close();
});
// A failed config cannot briefly expose machine classification or enable an untracked submission.
test("configuration failure keeps machine hints hidden and blocks review until reload", async () => {
  const base = responder();
  const page = await mount(browser, entry, "default", {}, (url, request) => url.pathname.endsWith("review-learning/config") ? { status: 503, message: "配置暂不可用" } : base.respond(url, request));
  await page.getByRole("button", { name: "查看候选 盲审材料 11" }).click();
  await page.getByRole("button", { name: "重新加载学习配置" }).waitFor();
  await page.getByLabel("拒绝说明").fill("独立审核理由");
  assert.equal(await page.getByRole("button", { name: "拒绝此原始材料" }).isDisabled(), true);
  assert.equal(await page.getByRole("region", { name: "系统文档分类" }).count(), 0);
  await page.close();
});

// An account change during the awaited submit event must not send the business write as the new user.
test("identity change while submitting never replays the old user's decision under a new token", async () => {
  const base = responder(); let release; let received;
  const submitted = new Promise(resolve => { received = resolve; });
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/events") && request.postDataJSON()?.event === "submit") { received(); return new Promise(resolve => { release = resolve; }); }
    return base.respond(url, request);
  });
  await page.getByRole("button", { name: "查看候选 盲审材料 11" }).click();
  await page.getByLabel("人工一级类型").selectOption("other");
  await page.getByLabel("拒绝说明").fill("前一用户的审核决定");
  await page.getByRole("button", { name: "拒绝此原始材料" }).click();
  await submitted;
  await page.evaluate(() => window.changeSession("account-B"));
  release({ state: "active" });
  await page.waitForTimeout(200);
  assert.equal(base.writes.filter(x => x.path.endsWith("/reject-unstructured")).length, 0);
  assert.equal(base.writes.filter(x => x.path.endsWith("/complete")).length, 0);
  await page.close();
});
// Corrections must append explicitly reasoned human labels, retaining audited action/field evidence.
test("sample correction requires a reason and preserves committed ground truth", async () => {
  const writes = []; const metrics = { sample_count: 1, primary_accuracy: 0, primary_denominator: 1, secondary_accuracy: null, secondary_denominator: 0, policy_precision: null, policy_precision_denominator: 0, policy_recall: null, policy_recall_denominator: 0, risk_agreement: null, risk_denominator: 0, action_agreement: 1, action_denominator: 1, field_agreement: 1, field_denominator: 1, error_types: {} };
  const human = { human_primary_type: "other", human_policy: false, human_action: "reject", human_field_decisions: { name: "reject" }, human_note: "原审核证据" };
  const page = await mount(browser, "src/app/admin/review-learning/page.tsx", "default", {}, (url, request) => {
    if (request.method() !== "GET") { writes.push({ path: url.pathname, body: request.postDataJSON() }); return { id: "corrected" }; }
    if (url.pathname.endsWith("/config")) return { enabled: true, actor_mode: "human" };
    if (url.pathname.endsWith("/performance")) return { sample_count: 1, windows: { all: metrics, recent_50: metrics, recent_100: metrics }, by_model_version: {} };
    if (url.pathname.endsWith("/examples")) return { items: [{ id: url.searchParams.get("offset") === "50" ? "sample-51" : "original", candidate_id: 11, human_ground_truth: human }], total: 51 };
    return { items: [] };
  });
  await page.getByRole("button", { name: "纠正人工类型", exact: true }).click();
  assert.equal(await page.getByRole("button", { name: "追加纠正版本" }).isDisabled(), true);
  await page.getByLabel("纠正后的人工一级类型").selectOption("result");
  await page.getByLabel("人工纠正原因").fill("  原文实际为获奖结果  ");
  await page.getByRole("button", { name: "追加纠正版本" }).click();
  await page.getByRole("button", { name: "纠正人工类型", exact: true }).waitFor();
  assert.deepEqual(writes, [{ path: "/api/admin/review-learning/examples/original/correct", body: { human_ground_truth: { human_primary_type: "result" }, reason: "原文实际为获奖结果" } }]);
  await page.getByRole("navigation", { name: "学习样本分页" }).getByRole("button", { name: "下一页" }).click();
  await page.getByText("样本 sample-51", { exact: false }).waitFor();
  await page.close();
});
// Historical machine wrapper labels must not reveal a type/risk before the independent label is chosen.
for (const enabled of [true, false]) test(`real-shaped collector metadata is ${enabled ? "blind" : "unchanged when disabled"}`, async () => {
  const base = responder({ enabled });
  const sourceTitle = "关于赛事政策与报名安排的原始说明";
  const row = { ...makeRow(), title: `学校材料 · 上海理工大学 · registration_notice · ${sourceTitle}`, risk_level: "HIGH_RISK", flags: ["DOCUMENT_UPDATE_REVIEW", "HIGH_RISK", "CONFLICT", "UNVERIFIED"], risk_reasons: ["DOCUMENT_POLICY_REVIEW", "LOW_RISK", "RELATION_CONFLICT"], collection_context: { kind: "school_mapping", school_name: "上海理工大学", notice_type: "registration_notice", source_quality: "B", source_title: sourceTitle, is_formal_recognition: false, evidence_notes: "原资料细分类为 national_notice_reprint，导入通知类型映射为 competition_notice。原文明确报名与政策依据应分别核验", published_at: "2026-10-01" } };
  row.description = 'collector:fixture\n' + JSON.stringify({ input: { source: { title: sourceTitle, body: "原文正文：2026 年报名截止为十月十五日。", university_notice: { notice_type: "registration_notice", is_formal_recognition: false, recognition_evidence: "原始附件第3条" } }, mapping: { notice_type: "registration_notice", risk_level: "HIGH_RISK", flags: ["DOCUMENT_UPDATE_REVIEW", "CONFLICT"] } }, document_classification: { primary_type: "policy", classification_reason: "不应泄漏的机器结论" } });
  row.relation = { candidate_id: 11, status: "pending", preview_token: "rel-blind", relation_kind: "notice", university_id: 2, competition_id: 3, notice_type: "registration_notice", school_name: "上海理工大学", year: 2026, prepared: {}, source: { source_title: sourceTitle, source_url: "https://example.test/source", publisher: "教务处", verification_state: "UNVERIFIED" }, flags: ["RELATION_CONFLICT"], blocking_reasons: ["来源尚未由管理员核验"], can_approve: false, existing_records: [], history: [] };
  const fallback = { ...makeRow(12), title: "学校材料 · 示例大学 · award_policy · 原文标题 · 保留原文分隔" };
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/field-reviews")) return { items: [row, fallback], total: 2 };
    if (url.pathname.endsWith("/field-reviews/11")) return { data: row };
    return base.respond(url, request);
  });
  const queue = page.getByRole("region", { name: "字段候选队列" });
  const title = enabled ? sourceTitle : row.title;
  await queue.getByRole("button", { name: `查看候选 ${title}`, exact: true }).click();
  const detail = page.getByRole("article", { name: "候选详情" });
  await detail.getByRole("heading", { name: title, exact: true }).waitFor();
  await detail.getByText("查看完整采集记录", { exact: true }).click();
  assert.match(await detail.innerText(), /原文正文：2026 年报名截止为十月十五日|原始附件第3条/);
  assert.match(await detail.innerText(), /原文明确报名与政策依据应分别核验/);
  assert.match(await queue.innerText(), /来源冲突|学校关系冲突/);
  if (enabled) {
    assert.doesNotMatch(await queue.innerText(), /学校材料|registration_notice|award_policy|DOCUMENT_|高风险|低风险/);
    assert.doesNotMatch(await detail.innerText(), /registration_notice|national_notice_reprint|competition_notice|DOCUMENT_|不应泄漏的机器结论|材料包含该赛事的认定依据|未提供该赛事的正式认定证据/);
    assert.doesNotMatch(await detail.locator("pre").first().innerText(), /notice_type|is_formal_recognition|risk_level|document_classification/);
    await detail.getByRole("heading", { name: "学校关系审核", exact: true }).waitFor();
    await queue.getByRole("button", { name: "查看候选 原文标题 · 保留原文分隔", exact: true }).waitFor();
    assert.equal(await page.getByLabel("人工一级类型").inputValue(), "");
  } else {
    assert.match(await queue.innerText(), /学校材料|registration_notice|DOCUMENT_UPDATE_REVIEW|高风险/);
    await detail.getByRole("heading", { name: "学校关系审核 · 报名通知", exact: true }).waitFor();
    assert.match(await detail.locator("pre").first().innerText(), /notice_type|document_classification/);
  }
  await page.close();
});
// Preparing raw material must not re-expose machine labels or rewrite source metadata as a side effect.
test("blind preparation renders safe source text while preserving original preparation payload", async () => {
  const base = responder(); const writes = [];
  const row = { ...makeRow(), title: "学校材料 · 示例学校 · registration_notice · 来源原文标题", source: { source_title: "来源原文标题" }, description: JSON.stringify({ body: "完整原文政策段落", notice_type: "registration_notice", risk_level: "HIGH_RISK" }) };
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/field-reviews")) return { items: [row], total: 1 };
    if (url.pathname.endsWith("/field-reviews/11")) return { data: row };
    if (url.pathname.endsWith("/prepare")) { writes.push(request.postDataJSON()); return { data: row }; }
    return base.respond(url, request);
  });
  await page.getByRole("button", { name: "查看候选 来源原文标题", exact: true }).click();
  await page.getByRole("button", { name: "整理为字段候选" }).click();
  assert.equal(await page.getByLabel("候选标题", { exact: true }).inputValue(), "来源原文标题");
  assert.match(await page.getByLabel("原始说明", { exact: true }).inputValue(), /完整原文政策段落/);
  assert.doesNotMatch(await page.getByLabel("原始说明", { exact: true }).inputValue(), /notice_type|registration_notice|HIGH_RISK/);
  await page.getByRole("button", { name: "移除此行" }).click();
  await page.getByRole("button", { name: "保存结构化字段，等待审核" }).click();
  await page.getByText("候选已保存，等待人工核验与字段审核。", { exact: true }).waitFor();
  assert.equal(writes[0].title, row.title);
  assert.equal(writes[0].description, row.description);
  await page.close();
});
// All supported human risk values remain explicit, optional choices, including baseline NORMAL.
test("optional normal risk is unselected until independently chosen and then reaches completion", async () => {
  const base = responder(); const page = await mount(browser, entry, "default", {}, base.respond);
  await page.getByRole("button", { name: "查看候选 盲审材料 11" }).click();
  await page.getByText("补充二级类型或风险（可选）", { exact: true }).click();
  const risk = page.getByLabel("人工风险判断");
  assert.equal(await risk.inputValue(), "");
  await risk.selectOption("NORMAL");
  await page.getByLabel("人工一级类型").selectOption("other");
  await page.getByLabel("拒绝说明").fill("独立判断为普通风险");
  await page.getByRole("button", { name: "拒绝此原始材料" }).click();
  await page.getByText("学习样本已保存", { exact: false }).waitFor();
  assert.deepEqual(base.writes.find(write => write.path.endsWith("/complete")).body, { human_primary_type: "other", human_risk_level: "NORMAL" });
  await page.close();
});
