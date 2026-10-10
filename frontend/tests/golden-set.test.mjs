import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium, mount, bundle } from "./browser-harness.mjs";

let browser;
before(async () => { browser = await chromium.launch({ headless: true, channel: "msedge" }); });
after(async () => { await browser?.close(); });
const entry = "src/app/admin/golden-set/page.tsx";
const types = [
  ["registration_notice", "报名通知"], ["organization_notice", "组织通知"], ["selection_notice", "校赛/选拔通知"],
  ["recommendation_notice", "推荐通知"], ["result_notice", "结果通知"], ["publicity_notice", "公示"],
  ["completion_news", "完赛新闻"], ["competition_intro", "赛事介绍"], ["event_news", "活动新闻"],
  ["policy_recognition_document", "竞赛认定政策"], ["award_policy_document", "竞赛奖励政策"],
  ["postgraduate_policy_document", "推免政策"], ["comprehensive_evaluation_policy_document", "综合测评政策"],
  ["innovation_credit_policy_document", "创新学分政策"], ["repost", "转载/转发"], ["deadline_extension", "延期通知"],
  ["correction_notice", "更正通知"], ["rule_update", "规则更新"], ["historical_material", "历史资料"], ["other", "其他"],
].map(([value, label]) => ({ value, label }));
const sources = [101, 102, 103].map((source_id, index) => ({
  source_id, title: `真实来源测试夹具 ${index + 1}`, school_name: index ? null : "测试大学", publisher: null,
  published_at: null, source_url: index ? "javascript:alert(1)" : "https://school.example.edu.cn/source",
  content_preview: "<script>没有执行</script> 原文摘要", body_available: true,
  predicted_type: "publicity_notice", predicted_confidence: 0.94,
  predicted_secondary_types: ["result_notice"], matched_rules: ["test_rule"], classification_reason: "测试机判解释",
  prediction_exposed: false, annotation: null,
}));
function fixture({ conflict = false, delaySave = 0, delayExposure = 0, exposureError = false, annotatedFirst = false } = {}) {
  const items = structuredClone(sources);
  const writes = [];
  const progress = () => ({ total: items.length, annotated: items.filter(x => x.annotation?.status === "annotated").length,
    draft: items.filter(x => x.annotation?.status === "draft").length, skipped: items.filter(x => x.annotation?.status === "skipped").length,
    untouched: items.filter(x => !x.annotation).length });
  const annotation = (item, body, revision = 1) => ({ ...body, source_id: item.source_id, title: item.title,
    predicted_type: item.predicted_type, predicted_confidence: item.predicted_confidence,
    annotated_by: "fixture-admin", annotated_at: "2026-10-01T12:00:00Z", skipped: body.status === "skipped", revision });
  if (annotatedFirst) items[0].annotation = annotation(items[0], { status: "annotated", human_primary_type: "result_notice", human_secondary_types: [], note: "已完成", prediction_exposed: false });
  const audits = { policies: [{ audit_id: "p1", title: "政策核验夹具", school_name: "测试大学", source_url: sources[0].source_url, content_preview: "政策正文", entries: [{ raw_competition_name: "样例赛事", evidence_text: "奖励条目" }], competition_name: null, raw_competition_name: null, recognition_type: null, annotation: null }], relations: [{ audit_id: "r1", title: "关系核验夹具", school_name: "测试大学", source_url: sources[0].source_url, content_preview: "关系正文", entries: [], competition_name: "样例赛事", raw_competition_name: "来源赛事", recognition_type: "award_recognition", annotation: null }] };
  const dataset = () => ({ dataset_id: "fixture-only", total: items.length, items: structuredClone(items), progress: progress(), document_types: types, audit_sets: { policies: 1, relations: 1 } });
  return { writes, items, respond: async (url, request) => {
    const path = url.pathname;
    if (request.method() !== "GET") writes.push({ path, method: request.method(), body: request.postDataJSON() });
    if (path.endsWith("/golden-set")) return dataset();
    if (path.includes("/exposure/")) {
      await new Promise(resolve => setTimeout(resolve, delayExposure));
      if (exposureError) return { status: 503, message: "曝光记录保存失败" };
      items.find(x => String(x.source_id) === path.split("/").at(-1)).prediction_exposed = true;
      return { prediction_exposed: true };
    }
    if (path.includes("/annotations/")) {
      await new Promise(resolve => setTimeout(resolve, delaySave));
      const item = items.find(x => String(x.source_id) === path.split("/").at(-1));
      const body = request.postDataJSON();
      if (conflict) { conflict = false; item.annotation = annotation(item, { status: "draft", human_primary_type: "other", human_secondary_types: [], note: "另一窗口的修改", prediction_exposed: false }, 2); return { status: 409, message: "版本冲突" }; }
      item.annotation = annotation(item, body, (item.annotation?.revision ?? 0) + 1);
      return { annotation: item.annotation, progress: progress() };
    }
    if (path.includes("/audits/")) {
      const [kind, id] = path.split("/audits/")[1].split("/");
      const list = audits[kind];
      if (request.method() === "PUT") { const item = list.find(x => x.audit_id === id); item.annotation = { ...request.postDataJSON(), revision: 1, annotated_by: "fixture-admin", annotated_at: "2026-10-01T12:00:00Z" }; return { annotation: item.annotation, progress: { total: 1, annotated: 1, draft: 0, skipped: 0, untouched: 0 } }; }
      return { items: structuredClone(list), progress: { total: 1, annotated: 0, draft: 0, skipped: 0, untouched: 1 }, checks: [{ key: "source_valid", label: "来源有效" }, { key: "match_correct", label: "匹配正确" }] };
    }
    if (path.endsWith("/metrics")) return { data: { status: "BLOCKED", human_n: 0, blind_human_n: 0, all_human: { human_n: 0, accuracy: null }, blind_human: { human_n: 0, accuracy: null }, readiness: { ready: false, blockers: ["尚未完成 100 条人工标注"] } } };
    if (path.endsWith("/export")) return { dataset_id: "fixture-only", annotations: [], policy_audits: [], relation_audits: [], metrics: { status: "BLOCKED" } };
    throw new Error(`Unexpected ${request.method()} ${path}`);
  } };
}

// Catches accidental prediction rendering, label prefilling and passive annotation writes.
test("blind startup has all 20 unselected types, plain source evidence and no writes", async () => {
  const f = fixture(); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("heading", { name: sources[0].title }).waitFor();
  assert.equal(await page.getByRole("radio").count(), 20);
  assert.equal(await page.getByRole("radio", { checked: true }).count(), 0);
  assert.equal(await page.getByText("测试机判解释").count(), 0);
  assert.equal(await page.getByRole("button", { name: "保存并下一条", exact: true }).isDisabled(), true);
  assert.equal(await page.getByRole("link", { name: "查看来源原文" }).getAttribute("rel"), "noopener noreferrer");
  await page.getByText("<script>没有执行</script> 原文摘要", { exact: true }).waitFor();
  assert.deepEqual(f.writes, []); await page.close();
});

// Catches navigation dropping local edits and treating selected labels as submitted annotations.
test("navigation preserves local draft, explicit draft and skip do not count as completed", async () => {
  const f = fixture(); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("radio", { name: "报名通知", exact: true }).check();
  await page.getByLabel("标注备注").fill("我的依据");
  await page.getByRole("button", { name: "下一条", exact: true }).click();
  assert.equal(await page.getByRole("link", { name: "查看来源原文" }).count(), 0);
  await page.getByRole("button", { name: "上一条", exact: true }).click();
  assert.equal(await page.getByLabel("标注备注").inputValue(), "我的依据");
  assert.equal(await page.getByRole("radio", { name: "报名通知", exact: true }).isChecked(), true);
  assert.deepEqual(f.writes, []);
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await page.getByText("草稿已保存", { exact: false }).waitFor();
  assert.equal(f.writes[0].body.status, "draft");
  assert.equal(f.writes[0].body.expected_revision, 0);
  await page.getByRole("button", { name: "跳过并下一条" }).click();
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  assert.equal(f.writes[1].body.status, "skipped");
  assert.equal(f.writes[1].body.expected_revision, 1);
  await page.getByText("已完成 0 / 3", { exact: false }).waitFor(); await page.close();
});

// Catches label keyboard defaults, IME/text capture and double submissions during pending writes.
test("keyboard maps explicit choices and Enter saves once while IME and text inputs are ignored", async () => {
  const f = fixture({ delaySave: 180 }); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("heading", { name: sources[0].title }).waitFor();
  await page.keyboard.press("4");
  assert.equal(await page.getByRole("radio", { name: "结果通知", exact: true }).isChecked(), true);
  await page.evaluate(() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "1", isComposing: true, bubbles: true })));
  assert.equal(await page.getByRole("radio", { name: "结果通知", exact: true }).isChecked(), true);
  await page.getByLabel("标注备注").focus(); await page.keyboard.press("1"); await page.keyboard.press("Enter");
  assert.deepEqual(f.writes, []);
  await page.getByLabel("标注备注").blur();
  await page.keyboard.press("Enter"); await page.keyboard.press("Enter");
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  assert.equal(f.writes.length, 1); assert.equal(f.writes[0].body.human_primary_type, "result_notice");
  assert.equal(f.writes[0].body.status, "annotated");
  await page.keyboard.press("Alt+ArrowLeft"); await page.getByRole("heading", { name: sources[0].title }).waitFor();
  await page.getByText("已完成 1 / 3", { exact: false }).waitFor(); await page.close();
});

// Catches displaying predictions before durable exposure acknowledgement or losing the exposure flag.
test("prediction is revealed only after exposure save and exposure survives navigation", async () => {
  const f = fixture({ delayExposure: 160 }); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("button", { name: "查看机器预测" }).click();
  assert.equal(await page.getByText("测试机判解释").count(), 0);
  await page.getByText("测试机判解释").waitFor();
  assert.equal(await page.getByRole("radio", { checked: true }).count(), 0);
  await page.getByRole("button", { name: "下一条", exact: true }).click();
  assert.equal(await page.getByText("测试机判解释").count(), 0);
  await page.getByRole("button", { name: "上一条", exact: true }).click();
  assert.equal(await page.getByText("测试机判解释").count(), 0);
  await page.getByText("曾查看机器预测", { exact: false }).waitFor();
  await page.getByRole("radio", { name: "报名通知", exact: true }).check();
  await page.getByRole("button", { name: "保存并下一条", exact: true }).click();
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  assert.equal(f.writes[1].body.prediction_exposed, true); await page.close();
});

test("failed exposure never reveals predictions", async () => {
  const f = fixture({ exposureError: true }); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("button", { name: "查看机器预测" }).click();
  await page.getByRole("alert").getByText("曝光记录保存失败", { exact: false }).waitFor();
  assert.equal(await page.getByText("测试机判解释").count(), 0); await page.close();
});

// Catches silent overwrite on stale revision; preserving then consciously rebasing needs a second save.
test("409 preserves local work and requires reviewing latest revision before a new save", async () => {
  const f = fixture({ conflict: true }); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("radio", { name: "报名通知", exact: true }).check();
  await page.getByLabel("标注备注").fill("本地依据");
  await page.getByRole("button", { name: "保存并下一条", exact: true }).click();
  await page.getByRole("alert").getByText("版本冲突", { exact: false }).waitFor();
  assert.equal(await page.getByLabel("标注备注").inputValue(), "本地依据");
  await page.getByRole("button", { name: "核对服务器最新版本" }).click();
  await page.getByText("另一窗口的修改", { exact: false }).waitFor();
  await page.getByRole("button", { name: "保留当前填写，以最新版本继续" }).click();
  assert.equal(f.writes.length, 1);
  await page.getByRole("button", { name: "保存并下一条", exact: true }).click();
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  assert.equal(f.writes[1].body.expected_revision, 2); assert.equal(f.writes[1].body.note, "本地依据"); await page.close();
});

// Catches losing restart progress or conflating audit checks with source labels.
test("server resume skips completed records and audit completion requires every explicit answer", async () => {
  const f = fixture({ annotatedFirst: true }); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  await page.getByRole("tab", { name: "政策核验", exact: false }).click();
  await page.getByRole("heading", { name: "政策核验夹具" }).waitFor();
  const section = page.getByRole("region", { name: "政策核验工作区" });
  assert.equal(await section.getByRole("button", { name: "保存并下一条", exact: true }).isDisabled(), true);
  await section.getByLabel("来源有效").selectOption("yes");
  assert.equal(await section.getByRole("button", { name: "保存并下一条", exact: true }).isDisabled(), true);
  await section.getByLabel("匹配正确").selectOption("unsure");
  await section.getByRole("button", { name: "保存并下一条", exact: true }).click();
  await section.getByText("已完成 1 / 1", { exact: false }).waitFor();
  assert.deepEqual(f.writes[0].body.answers, { source_valid: "yes", match_correct: "unsure" });
  await page.getByRole("tab", { name: "关系核验", exact: false }).click();
  await page.getByRole("heading", { name: "关系核验夹具" }).waitFor(); await page.close();
});

test("metrics stay unavailable without human labels and export downloads the server snapshot", async () => {
  const f = fixture(); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("tab", { name: "评估与导出" }).click();
  await page.getByText("尚未完成 100 条人工标注", { exact: true }).waitFor();
  await page.getByText("主类型标注不能证明不存在截止日期、规则或事实变化", { exact: false }).waitFor();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出标注与评估 JSON" }).click();
  const download = await downloadPromise; assert.match(download.suggestedFilename(), /golden-set.*\.json$/);
  assert.deepEqual(f.writes, []); await page.close();
});


// Radio choice is not text entry: Enter must still submit the selected human label.
test("Enter after a radio selection submits, and optional safety answer is explicit", async () => {
  const f = fixture(); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("radio", { name: "结果通知", exact: true }).check();
  assert.equal(await page.getByLabel("可供信息参考且无重要变更？（可选）").inputValue(), "");
  await page.getByLabel("可供信息参考且无重要变更？（可选）").selectOption("no");
  await page.getByRole("radio", { name: "结果通知", exact: true }).focus();
  await page.keyboard.press("Enter");
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  assert.equal(f.writes[0].body.informational_safe, "no"); await page.close();
});

// Navigation persists local edits across refresh, but never shares them with a different account.
test("tab drafts survive refresh without downgrading completed server labels and remain account scoped", async () => {
  const f = fixture({ annotatedFirst: true }); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  await page.getByRole("button", { name: "上一条", exact: true }).click();
  await page.getByLabel("标注备注").fill("待补充的本地依据");
  await page.getByRole("button", { name: "下一条", exact: true }).click();
  await page.reload(); await page.addScriptTag({ content: bundle(entry) });
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  await page.getByRole("button", { name: "上一条", exact: true }).click();
  assert.equal(await page.getByLabel("标注备注").inputValue(), "待补充的本地依据");
  await page.getByText("本标签页草稿", { exact: false }).first().waitFor();
  assert.equal(f.items[0].annotation.status, "annotated"); assert.deepEqual(f.writes, []);
  await page.evaluate(() => window.changeSession("account-B"));
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  await page.getByRole("button", { name: "上一条", exact: true }).click();
  assert.equal(await page.getByLabel("标注备注").inputValue(), "已完成"); await page.close();
});


// A later exposure event must not misstate the provenance of an already saved blind annotation.
test("revealing after a saved blind label explains that only the next save is exposed", async () => {
  const f = fixture({ annotatedFirst: true }); const page = await mount(browser, entry, "default", {}, f.respond);
  await page.getByRole("heading", { name: sources[1].title }).waitFor();
  await page.getByRole("button", { name: "上一条", exact: true }).click();
  await page.getByRole("button", { name: "查看机器预测" }).click();
  await page.getByText("已保存的标注保持盲标记录", { exact: false }).waitFor();
  assert.equal(f.items[0].annotation.prediction_exposed, false); await page.close();
});

// Source validity cannot be judged if the original URL, policy dates and attachment evidence disappear.
test("audit retains original URL, publisher, effective dates and safe evidence links", async () => {
  const f = fixture(); const original = f.respond;
  const page = await mount(browser, entry, "default", {}, async (url, request) => {
    const result = await original(url, request);
    if (request.method() === "GET" && url.pathname.endsWith("/audits/policies")) result.items[0] = {
      ...result.items[0], publisher: "测试教务处", published_at: "2026-01-02", effective_from: "2026-02-01", effective_until: "2026-12-31",
      policy_url: "https://school.example.edu.cn/policy", attachment_url: "https://school.example.edu.cn/catalogue.pdf", blocking_reasons: ["附件范围待核对"],
      entries: [{ matched_competition_id: 77, evidence_text: "政策条目原文" }],
    };
    return result;
  });
  await page.getByRole("heading", { name: sources[0].title }).waitFor();
  await page.getByText(sources[0].source_url, { exact: true }).waitFor();
  await page.getByRole("tab", { name: "政策核验", exact: true }).click();
  await page.getByText("测试教务处", { exact: true }).waitFor();
  await page.getByText("2026-02-01", { exact: true }).waitFor();
  await page.getByText("2026-12-31", { exact: true }).waitFor();
  await page.getByText("附件范围待核对", { exact: false }).waitFor();
  assert.equal(await page.getByRole("link", { name: "查看政策页面" }).getAttribute("href"), "https://school.example.edu.cn/policy");
  assert.equal(await page.getByRole("link", { name: "查看政策附件" }).getAttribute("rel"), "noopener noreferrer");
  await page.getByText("匹配赛事 ID", { exact: true }).waitFor();
  assert.deepEqual(f.writes, []); await page.close();
});
