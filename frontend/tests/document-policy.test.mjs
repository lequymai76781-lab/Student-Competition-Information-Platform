import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium, mount } from "./browser-harness.mjs";

let browser;
before(async () => { browser = await chromium.launch({ headless: true, channel: "msedge" }); });
after(async () => { await browser?.close(); });

const entry = "src/app/admin/document-policy/page.tsx";
const classification = {
  document_type: "publicity_notice", primary_type: "publicity_notice",
  secondary_types: ["result_notice"], confidence: 0.93,
  classification_reason: "标题包含获奖名单公示", matched_rules: ["title_publicity"],
  classification_status: "AUTO_CLASSIFIED", requires_human_confirmation: false,
  informational_only: false, risk_level: "NORMAL", rule_version: "rules-v1",
};
const document = { id: 11, title: "校赛获奖名单公示", source_url: "https://school.example.edu.cn/notice", school_name: "示例大学", competition_name: "示例竞赛", status: "pending", classification };
const policy = {
  id: 7, title: "竞赛奖励政策", source_url: "https://school.example.edu.cn/policy",
  university_id: 2, school_name: "示例大学", classification: { ...classification, document_type: "award_policy_document", primary_type: "award_policy_document", secondary_types: [] },
  analysis: { automatic_relations: 1, requires_human_confirmation: true, blocking_reasons: ["附件待核验"], conflicts: [], entries: [{
    raw_competition_name: "全国示例竞赛", normalized_name: "全国示例竞赛", recognition_type: "award_recognition",
    match_status: "AUTO_MATCHED", match_confidence: 0.95, matched_competition_id: 9,
    match_reason: "正式名称精确匹配", verification_method: "AUTO_POLICY_MATCH", relation_status: "AUTO_RECOGNIZED",
    blocking_reasons: [], source_title: "竞赛奖励政策", source_url: "https://school.example.edu.cn/policy",
    effective_from: "2026-01-01", effective_to: "2026-12-31",
  }, {
    raw_competition_name: "相近赛事", normalized_name: "相近赛事", recognition_type: "award_recognition",
    match_status: "NEEDS_CONFIRMATION", match_confidence: 0.64, matched_competition_id: null,
    match_reason: "名称存在歧义", verification_method: null, relation_status: "NEEDS_HUMAN_REVIEW",
    blocking_reasons: ["同名赛事待确认"], source_title: "竞赛奖励政策", source_url: "https://school.example.edu.cn/policy",
    effective_from: null, effective_to: null,
  }] },
};

function respond(writes, { correctionError = false, analyzeError = false, matchError = false } = {}) {
  let matchedAnalysis = null;
  return (url, request) => {
    if (request.method() !== "GET") writes.push({ path: url.pathname, method: request.method(), body: request.postDataJSON() });
    if (url.pathname.endsWith("/classification") && request.method() === "PUT") {
      return correctionError ? { status: 409, message: "分类已变化，请重新加载" } : { data: { ...document, classification: { ...classification, document_type: "registration_notice", primary_type: "participation", secondary_type: "registration", classification_status: "HUMAN_CORRECTED" } } };
    }
    if (url.pathname.endsWith("/replay-classification")) return { data: { processed: 1 } };
    if (url.pathname.endsWith("/analyze")) return analyzeError ? { status: 422, message: "政策附件待人工核验" } : { data: policy };
    if (url.pathname.endsWith("/matches") && request.method() === "PUT") {
      if (matchError) return { status: 409, message: "候选赛事已变化" };
      matchedAnalysis = { ...policy.analysis, human_confirmed_relations: 1, entries: policy.analysis.entries.map((entry) => entry.raw_competition_name === "相近赛事" ? { ...entry, match_status: "HUMAN_CONFIRMED", verification_method: "HUMAN_POLICY_MATCH", matched_competition_id: 10, match_reason: "已人工核对" } : entry) };
      return { data: matchedAnalysis };
    }
    if (url.pathname.endsWith("/policies")) return { items: [{ ...policy, analysis: matchedAnalysis ?? policy.analysis }], total: 1 };
    if (url.pathname.endsWith("/document-policy")) return { items: [document], total: 1, statistics: { AUTO_CLASSIFIED: 1 }, document_types: [{ value: "publicity_notice", label: "公示" }, { value: "result_notice", label: "结果通知" }] };
    throw new Error(`Unexpected ${request.method()} ${url.pathname}`);
  };
}

// A passive visit must leave automatic classification and policy relationships unchanged.
test("classification is explained on read and passive loading never mutates records", async () => {
  const writes = [];
  const page = await mount(browser, entry, "default", {}, respond(writes));
  await page.getByRole("heading", { name: "来源文档分类与政策分析" }).waitFor();
  await page.getByText("校赛获奖名单公示").waitFor();
  await page.getByText("系统分类：结果/公示").waitFor();
  await page.getByText("二级标签（可选）：公示、结果通知").waitFor();
  await page.getByText("93%", { exact: false }).waitFor();
  await page.getByText("标题包含获奖名单公示").waitFor();
  await page.getByText("系统自动识别，无需再次选择类型", { exact: false }).waitFor();
  assert.equal(await page.getByRole("link", { name: "查看来源原文" }).getAttribute("href"), document.source_url);
  assert.deepEqual(writes, []);
  await page.close();
});

// A failed correction must remain visible and must not claim a saved classification.
test("explicit correction sends reason and reports API conflict without changing displayed type", async () => {
  const writes = [];
  const page = await mount(browser, entry, "default", {}, respond(writes, { correctionError: true }));
  await page.getByText("校赛获奖名单公示").waitFor();
  await page.getByRole("button", { name: "修改分类" }).click();
  await page.getByLabel("修正后的文档类型").selectOption("participation");
  await page.getByLabel("分类修正依据").fill("原文为获奖结果");
  await page.getByRole("button", { name: "保存分类修正" }).click();
  await page.getByRole("alert").getByText("分类已变化，请重新加载").waitFor();
  assert.deepEqual(writes, [{ path: "/api/admin/document-policy/11/classification", method: "PUT", body: { document_type: "participation", reason: "原文为获奖结果" } }]);
  assert.equal(await page.getByText("系统分类：结果/公示").count(), 1);
  await page.close();
});

// A successful audited correction updates the visible type; replay remains a separate explicit action.
test("saved correction updates the display and replay runs only after its own click", async () => {
  const writes = [];
  const page = await mount(browser, entry, "default", {}, respond(writes));
  await page.getByText("校赛获奖名单公示").waitFor();
  await page.getByRole("button", { name: "修改分类" }).click();
  await page.getByLabel("修正后的文档类型").selectOption("participation");
  await page.getByLabel("分类修正依据").fill("原文以组织参赛为主");
  await page.getByRole("button", { name: "保存分类修正" }).click();
  await page.getByText("系统分类：参赛相关").waitFor();
  assert.deepEqual(writes, [{ path: "/api/admin/document-policy/11/classification", method: "PUT", body: { document_type: "participation", reason: "原文以组织参赛为主" } }]);
  await page.getByRole("button", { name: "回放已保存材料分类" }).click();
  await page.getByText("分类回放已完成", { exact: false }).waitFor();
  assert.deepEqual(writes[1], { path: "/api/admin/document-policy/replay-classification", method: "POST", body: {} });
  await page.close();
});

// Policy evidence must survive the summary view and analysis must require a click.
test("policy analysis shows each relation and its evidence, with manual blockers", async () => {
  const writes = [];
  const page = await mount(browser, entry, "default", {}, respond(writes, { analyzeError: true }));
  await page.getByRole("tab", { name: "政策分析结果" }).click();
  await page.getByText("竞赛奖励政策", { exact: true }).waitFor();
  await page.getByText("全国示例竞赛", { exact: true }).waitFor();
  await page.getByText("同名赛事待确认", { exact: false }).waitFor();
  await page.getByText("附件待核验", { exact: false }).waitFor();
  await page.getByText("2026-01-01", { exact: false }).waitFor();
  assert.equal(await page.getByRole("link", { name: "查看政策原文" }).first().getAttribute("href"), policy.source_url);
  assert.deepEqual(writes, []);
  await page.getByRole("button", { name: "分析政策 竞赛奖励政策" }).click();
  await page.getByRole("alert").getByText("政策附件待人工核验").waitFor();
  assert.deepEqual(writes, [{ path: "/api/admin/document-policy/policies/7/analyze", method: "POST", body: {} }]);
  await page.close();
});

// Quick confirmation must be a named, audited choice; it cannot silently choose the first candidate.
test("ambiguous policy match requires explicit competition and reason", async () => {
  const writes = [];
  const row = { ...policy, analysis: { ...policy.analysis, entries: policy.analysis.entries.map((entry) => entry.raw_competition_name === "相近赛事" ? { ...entry, match_status: "NEEDS_QUICK_CONFIRM", candidate_ids: [9, 10] } : entry) } };
  let stored = row;
  const handle = respond(writes);
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/policies")) return { items: [stored], total: 1 };
    const result = handle(url, request);
    if (url.pathname.endsWith("/matches") && request.method() === "PUT") stored = { ...stored, analysis: result.data };
    return result;
  });
  await page.getByRole("tab", { name: "政策分析结果" }).click();
  await page.getByRole("region", { name: "政策条目 相近赛事" }).waitFor();
  assert.deepEqual(writes, []);
  const matchEntry = page.getByRole("region", { name: "政策条目 相近赛事" });
  assert.equal(await matchEntry.getByRole("button", { name: "确认赛事匹配" }).isDisabled(), true);
  await matchEntry.getByLabel("匹配赛事 ID").selectOption("10");
  await matchEntry.getByLabel("匹配确认依据").fill("已核对政策附件所列全称");
  await matchEntry.getByRole("button", { name: "确认赛事匹配" }).click();
  await matchEntry.getByText("赛事 #10", { exact: false }).waitFor();
  assert.deepEqual(writes, [{ path: "/api/admin/document-policy/policies/7/matches", method: "PUT", body: { raw_competition_name: "相近赛事", competition_id: 10, reason: "已核对政策附件所列全称" } }]);
  await page.close();
});

// A bounded list must still expose records beyond the first API page.
test("classification pagination loads later stored sources", async () => {
  const offsets = [];
  const page = await mount(browser, entry, "default", {}, (url) => {
    if (url.pathname.endsWith("/document-policy")) {
      offsets.push(url.searchParams.get("offset") ?? "0");
      const later = url.searchParams.get("offset") === "50";
      return { items: [{ ...document, id: later ? 61 : 11, title: later ? "后续来源材料" : document.title }], total: 51, statistics: { AUTO_CLASSIFIED: 51 }, document_types: [{ value: "publicity_notice", label: "公示" }] };
    }
    if (url.pathname.endsWith("/policies")) return { items: [], total: 0 };
    throw new Error(`Unexpected ${url.pathname}`);
  });
  await page.getByText("校赛获奖名单公示").waitFor();
  await page.getByRole("button", { name: "下一页来源" }).click();
  await page.getByText("后续来源材料").waitFor();
  assert.ok(offsets.includes("50"));
  await page.close();
});

// An ordinary school notice should expose participation evidence without implying policy recognition.
test("school registration evidence is visibly source-only", async () => {
  const source = { ...document, title: "报名通知", relation_evidence: { relation_type: "participation_evidence", status: "evidence_only", source_url: "https://school.example.edu.cn/registration" } };
  const page = await mount(browser, entry, "default", {}, (url) => url.pathname.endsWith("/document-policy")
    ? { items: [source], total: 1, document_types: [{ value: "registration_notice", label: "报名通知" }] }
    : { items: [], total: 0 });
  await page.getByText("报名通知").waitFor();
  await page.getByText("仅作为参赛证据，不代表正式政策认可", { exact: false }).waitFor();
  assert.equal(await page.getByRole("link", { name: "查看参赛证据来源" }).getAttribute("href"), source.relation_evidence.source_url);
  await page.close();
});

// A newer policy can invalidate an earlier analysis during the same page session.
test("analyzing a conflicting policy refreshes the older card instead of keeping stale automatic status", async () => {
  const old = { ...policy, id: 4, title: "旧版推免竞赛目录", analysis: null };
  const newer = { ...policy, id: 5, title: "新版推免竞赛目录", analysis: null };
  const oldAutomatic = { ...policy.analysis, automatic_relations: 1, requires_human_confirmation: false, blocking_reasons: [], entries: [policy.analysis.entries[0]] };
  const oldBlocked = { ...oldAutomatic, automatic_relations: 0, requires_human_confirmation: true,
    blocking_reasons: ["policy_version_conflict: 同范围新旧政策未明确替代关系"],
    entries: [{ ...oldAutomatic.entries[0], relation_status: "NEEDS_HUMAN_REVIEW", blocking_reasons: ["policy_version_conflict: 同范围新旧政策未明确替代关系"] }] };
  const newBlocked = { ...oldBlocked, conflicts: [{ policy_document_id: 4, title: old.title }] };
  let oldStored = null;
  let newStored = null;
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/policies")) return { items: [{ ...old, analysis: oldStored }, { ...newer, analysis: newStored }], total: 2 };
    if (url.pathname.endsWith("/policies/4/analyze") && request.method() === "POST") { oldStored = oldAutomatic; return { data: oldAutomatic }; }
    if (url.pathname.endsWith("/policies/5/analyze") && request.method() === "POST") { oldStored = oldBlocked; newStored = newBlocked; return { data: newBlocked }; }
    if (url.pathname.endsWith("/document-policy")) return { items: [], total: 0, document_types: [] };
    throw new Error(`Unexpected ${request.method()} ${url.pathname}`);
  });
  await page.getByRole("tab", { name: "政策分析结果" }).click();
  const oldCard = page.locator("article").filter({ hasText: old.title });
  await oldCard.getByRole("button", { name: `分析政策 ${old.title}` }).click();
  await oldCard.getByText("已自动建立关系 1 条", { exact: false }).waitFor();
  const newCard = page.locator("article").filter({ hasText: newer.title });
  await newCard.getByRole("button", { name: `分析政策 ${newer.title}` }).click();
  await newCard.getByText("已自动建立关系 0 条", { exact: false }).waitFor();
  await oldCard.getByText("已自动建立关系 0 条", { exact: false }).waitFor();
  await oldCard.getByText("同范围新旧政策未明确替代关系", { exact: false }).first().waitFor();
  await page.close();
});
