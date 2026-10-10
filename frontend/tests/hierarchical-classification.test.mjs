import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium, mount } from "./browser-harness.mjs";

let browser;
before(async () => { browser = await chromium.launch({ headless: true, channel: "msedge" }); });
after(async () => { await browser?.close(); });

const component = "src/components/DocumentClassification.tsx";
const entry = "src/app/admin/document-policy/page.tsx";
const base = {
  primary_type: "participation", document_type: "registration_notice", secondary_type: "registration",
  secondary_types: ["organization_notice"], confidence: 0.96, hierarchy_version: "hierarchy-v1",
  classification_status: "AUTO_CLASSIFIED", requires_human_confirmation: false, informational_only: false,
  risk_level: "NORMAL", classification_reason: "原文要求学生报名参赛", matched_rules: ["title_registration"],
  policy_assessment: { is_policy: false, policy_confidence: 0.03, policy_reason: "普通报名通知", policy_status: "NON_POLICY", positive_evidence: [], negative_evidence: ["报名通知"] },
};
const labels = ["参赛相关", "结果/公示", "赛事信息", "政策/认定", "更新/更正", "转发", "其他"];

// Catch accidentally using retained fine types as the routing label or requiring a semantic choice.
test("automatic primary classification is Chinese and optional while fine semantics never block review", async () => {
  const writes = [];
  const page = await mount(browser, component, "DocumentClassification", { classification: base, candidateId: 41 }, (url, request) => { writes.push(request.method()); return {}; });
  await page.getByRole("region", { name: "系统文档分类" }).waitFor();
  const body = await page.locator("body").innerText();
  assert.match(body, /系统分类：参赛相关/);
  assert.match(body, /系统自动识别/);
  assert.match(body, /二级标签.*报名/);
  assert.match(body, /字段.*关系.*单独审核/);
  assert.doesNotMatch(body, /participation|registration_notice|title_registration|NON_POLICY/);
  assert.equal(await page.getByRole("combobox").count(), 0);
  assert.equal(await page.getByRole("button", { name: "修改分类" }).count(), 1);
  assert.deepEqual(writes, []);
  await page.close();
});

// Catch missing/fine legacy primary values and untranslated future enum values.
test("legacy fine types map to Chinese primary labels without exposing unknown enums", async () => {
  for (const [document_type, primary_type, expected] of [
    ["selection_notice", undefined, "参赛相关"], ["publicity_notice", "publicity_notice", "结果/公示"],
    ["completion_news", undefined, "赛事信息"], ["award_policy_document", undefined, "政策/认定"],
    ["correction_notice", undefined, "更新/更正"], ["repost", undefined, "转发"],
    ["future_semantic_code", "future_primary_code", "其他"],
  ]) {
    const page = await mount(browser, component, "DocumentClassification", { classification: { ...base, document_type, primary_type, secondary_type: "future_secondary_code", secondary_types: [] } }, () => ({}));
    await page.getByRole("region", { name: "系统文档分类" }).waitFor();
    const body = await page.locator("body").innerText();
    assert.match(body, new RegExp(`系统分类：${expected}`));
    assert.doesNotMatch(body, /future_.*_code/);
    await page.close();
  }
});

// Catch a fine-grained or incomplete correction selector, optional reason, or unintended writes.
test("optional correction offers exactly seven primary choices and writes only the reasoned choice", async () => {
  const writes = [];
  const record = { id: 41, title: "报名材料", status: "pending", classification: base };
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (request.method() !== "GET") {
      writes.push({ path: url.pathname, method: request.method(), body: request.postDataJSON() });
      return { data: { ...record, classification: { ...base, primary_type: "result", document_type: "result_notice", secondary_type: "result", classification_status: "HUMAN_CONFIRMED" } } };
    }
    return url.pathname.endsWith("/document-policy") ? { items: [record], total: 1, document_types: ["registration_notice", "result_notice"] } : { items: [], total: 0 };
  });
  await page.getByRole("button", { name: "修改分类" }).click();
  const selector = page.getByRole("combobox");
  assert.deepEqual(await selector.locator("option").allTextContents(), labels);
  assert.equal(await selector.inputValue(), "participation");
  assert.equal(await page.getByRole("button", { name: "保存分类修正" }).isDisabled(), true);
  await selector.selectOption("result");
  await page.getByLabel("分类修正依据").fill("   ");
  assert.equal(await page.getByRole("button", { name: "保存分类修正" }).isDisabled(), true);
  await page.getByLabel("分类修正依据").fill("  正文为获奖结果  ");
  await page.getByRole("button", { name: "保存分类修正" }).click();
  await page.getByText("系统分类：结果/公示").waitFor();
  assert.deepEqual(writes, [{ path: "/api/admin/document-policy/41/classification", method: "PUT", body: { document_type: "result", reason: "正文为获奖结果" } }]);
  assert.equal(await page.getByRole("combobox").count(), 0);
  await page.close();
});

// Catch treating a classified update as safe, including update signals inside another primary.
test("updates and high-risk news retain mandatory field review despite automatic classification", async () => {
  for (const primary_type of ["update", "information"]) {
    const page = await mount(browser, component, "DocumentClassification", { classification: { ...base, primary_type, document_type: "correction_notice", secondary_type: "correction", risk_level: "HIGH_RISK" } }, () => ({}));
    await page.getByRole("region", { name: "系统文档分类" }).waitFor();
    const body = await page.locator("body").innerText();
    assert.match(body, /高风险/);
    assert.match(body, /字段审核/);
    assert.match(body, /分类.*不.*批准/);
    assert.doesNotMatch(body, /HIGH_RISK|AUTO_CLASSIFIED/);
    await page.close();
  }
});

// Catch hiding the independent policy uncertainty just because the routing primary is known.
test("uncertain policy evidence is Chinese and does not imply approval of policy relations", async () => {
  const page = await mount(browser, component, "DocumentClassification", { classification: { ...base, primary_type: "policy", document_type: "award_policy_document", secondary_type: "award", policy_assessment: { is_policy: false, policy_confidence: 0.68, policy_status: "NEEDS_POLICY_CONFIRM", policy_reason: "附件不足以确认政策结构", positive_evidence: ["奖励办法"], negative_evidence: ["附件缺失"] } } }, () => ({}));
  await page.getByRole("region", { name: "系统文档分类" }).waitFor();
  const body = await page.locator("body").innerText();
  assert.match(body, /政策判定：待人工确认/);
  assert.match(body, /68%/);
  assert.match(body, /附件不足以确认政策结构/);
  assert.match(body, /政策.*分类.*不.*认可/);
  assert.doesNotMatch(body, /NEEDS_POLICY_CONFIRM|award_policy_document/);
  await page.close();
});

// Catch treating forwarded material as original authoritative policy evidence.
test("reposted policy keeps its referenced Chinese primary and source-evidence limitation", async () => {
  const page = await mount(browser, component, "DocumentClassification", { classification: { ...base, primary_type: "repost", document_type: "repost", secondary_type: "repost", referenced_primary_type: "policy" } }, () => ({}));
  await page.getByRole("region", { name: "系统文档分类" }).waitFor();
  const body = await page.locator("body").innerText();
  assert.match(body, /系统分类：转发/);
  assert.match(body, /转发内容类型：政策\/认定/);
  assert.match(body, /原始官方依据/);
  assert.doesNotMatch(body, /repost|referenced_primary_type/);
  await page.close();
});

// Catch raw status, method and reason codes leaking through the complete administration flow.
test("admin source and policy views translate operational enums and coded blockers", async () => {
  const page = await mount(browser, entry, "default", {}, (url) => url.pathname.endsWith("/document-policy")
    ? { items: [{ id: 41, title: "待审核材料", status: "pending", classification: base }], total: 1 }
    : { items: [{ id: 7, title: "认定政策", classification: { ...base, primary_type: "policy" }, analysis: { automatic_relations: 0, requires_human_confirmation: true, blocking_reasons: ["policy_version_conflict: 同范围新旧政策未明确替代关系"], conflicts: [], entries: [{ raw_competition_name: "示例赛事", recognition_type: "award_recognition", match_status: "NEEDS_CONFIRMATION", relation_status: "HUMAN_RECOGNIZED", verification_method: "HUMAN_POLICY_MATCH", match_reason: "human_confirmed", blocking_reasons: ["official_source: 尚未核实官方来源"] }] } }], total: 1 });
  await page.getByText("待审核材料").waitFor();
  assert.doesNotMatch(await page.locator("body").innerText(), /pending|participation|title_registration/);
  await page.getByRole("tab", { name: "政策分析结果" }).click();
  await page.getByRole("heading", { name: "示例赛事" }).waitFor();
  const body = await page.locator("body").innerText();
  assert.match(body, /人工.*匹配/);
  assert.match(body, /同范围新旧政策未明确替代关系/);
  assert.match(body, /尚未核实官方来源/);
  assert.doesNotMatch(body, /NEEDS_CONFIRMATION|HUMAN_RECOGNIZED|HUMAN_POLICY_MATCH|human_confirmed|policy_version_conflict|official_source/);
  await page.close();
});
