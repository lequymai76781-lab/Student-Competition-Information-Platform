import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium, mount } from "./browser-harness.mjs";

let browser;
before(async () => { browser = await chromium.launch({ headless: true, channel: "msedge" }); });
after(async () => { await browser?.close(); });
const entry = "src/app/admin/field-review/page.tsx";
const source = (title, verified = true) => ({ source_type: "organizer_notice", source_title: title, source_url: "https://example.test/notice", publisher: "主办方", published_at: "2026-09-01T00:00:00Z", collected_at: "2026-09-27T00:00:00Z", verified_at: verified ? "2026-09-27T01:00:00Z" : null, verified_by: verified ? 9 : null, verification_state: verified ? "VERIFIED" : "UNVERIFIED" });
const proposal = (id, value, verified = true) => ({ id, candidate_value: value, source: source(`来源 ${id}`, verified), confidence: 0.8 });
const field = (name, label, oldValue, value, proposals, change = "modify") => ({ field_name: name, display_name: label, current_value: oldValue, candidate_value: value, changed: true, change_type: change, verification_state: "UNVERIFIED", source: proposals[0].source, source_url: proposals[0].source.source_url, source_type: "organizer_notice", confidence: 0.8, last_verified_at: null, decision: "pending", proposals });
const candidate = () => ({ id: 11, title: "秋季赛事候选", description: "人工核对候选", entity_type: "competition", competition_id: 3, competition_name: "现有赛事", edition_id: null, year: null, university_id: null, submitter_id: 4, origin: "user_submission", status: "pending", created_at: "2026-09-27T00:00:00Z", preview_token: "revision-1", fields: [field("name", "赛事名称", "原名称", "新名称", [proposal("p1", "新名称"), proposal("p2", "冲突名称")]), field("description", "赛事介绍", "原介绍", "新介绍", [proposal("p3", "新介绍", false)])], flags: ["CONFLICT", "UNVERIFIED"], history: [], bulk_eligible_fields: [] });
const config = { fields: { competition: [{ field_name: "name", display_name: "赛事名称", value_type: "string" }, { field_name: "description", display_name: "赛事介绍", value_type: "string" }], edition: [{ field_name: "registration_deadline", display_name: "报名截止", value_type: "datetime" }] }, source_types: [{ value: "organizer_notice", label: "主办方通知", priority: 90 }, { value: "manual_entry", label: "人工录入", priority: 20 }] };

test("school mapping keeps policy evidence separate and cannot prepare competition fields", async () => {
  const row = candidate();
  row.fields = []; row.flags = ["edition_uncertain", "UNVERIFIED"];
  row.collection_context = { kind: "school_mapping", school_name: "地方示例大学", notice_type: "registration_notice",
    source_quality: "B", edition_status: "edition_uncertain", year: null, is_formal_recognition: false,
    evidence_notes: "教务处组织报名", source_failure_reason: null };
  const page = await mount(browser, entry, "default", {}, respondWith(() => row));
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  await page.getByText("地方示例大学", { exact: true }).waitFor();
  await page.getByRole("region", { name: "采集材料摘要" }).getByText("报名通知", { exact: true }).waitFor();
  await page.getByText("未提供该赛事的正式认定证据", { exact: false }).waitFor();
  assert.equal(await page.getByRole("button", { name: "整理为字段候选" }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "提交字段审核", exact: true }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "拒绝此原始材料" }).isDisabled(), true);
  await page.close();
});

test("policy recognition remains pending and source failures remain visible", async () => {
  const row = candidate(); row.fields = [];
  row.collection_context = { kind: "school_mapping", school_name: "地方示例大学", notice_type: "policy_recognition",
    source_quality: "B", edition_status: "year_known_pending_edition", year: 2025, is_formal_recognition: true,
    recognition_evidence: "校教发〔2025〕1号附件第3项", source_failure_reason: "timeout", published_at: "2019-03-22" };
  const page = await mount(browser, entry, "default", {}, respondWith(() => row));
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  await page.getByRole("region", { name: "采集材料摘要" }).getByText("正式认定政策", { exact: true }).waitFor();
  await page.getByText("校教发〔2025〕1号附件第3项", { exact: true }).waitFor();
  await page.getByText("来源访问失败：timeout", { exact: true }).waitFor();
  await page.getByText("原文发布时间：2019-03-22（日期精度）", { exact: false }).waitFor();
  assert.equal(await page.getByRole("button", { name: "批量批准低风险字段" }).count(), 0);
  await page.close();
});
function respondWith(getCandidate, observed = []) {
  return (url, request) => {
    observed.push({ url, method: request.method(), body: request.postDataJSON() });
    if (url.pathname.endsWith("/config")) return config;
    if (/field-reviews\/11$/.test(url.pathname)) return { data: getCandidate() };
    if (url.pathname.endsWith("/field-reviews")) return { items: [getCandidate()], total: 1 };
    return { data: getCandidate() };
  };
}

// Catches accidental approve-all or choosing the first conflicting proposal automatically.
test("field review submits only the explicitly selected field and chosen conflicting proposal", async () => {
  let row = candidate();
  const writes = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/review")) {
      const payload = request.postDataJSON(); writes.push(payload);
      row = { ...row, status: "partially_approved", preview_token: "revision-2", fields: row.fields.map((f) => f.field_name === "name" ? { ...f, current_value: "冲突名称", decision: "approved" } : f), history: [{ reviewer_id: 9, reviewed_at: "2026-09-27T02:00:00Z", note: payload.note, decisions: payload.decisions, before: { name: "原名称" }, after: { name: "冲突名称" }, sources: [] }] };
      return { data: row };
    }
    return respondWith(() => row)(url, request);
  });
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  assert.equal(await page.getByRole("button", { name: "提交字段审核", exact: true }).isDisabled(), true);
  await page.getByLabel("赛事名称的处理方式").selectOption("approve");
  assert.equal(await page.getByRole("button", { name: "提交字段审核", exact: true }).isDisabled(), true);
  await page.getByLabel("采用赛事名称候选 2").check();
  await page.getByLabel("审核意见", { exact: true }).fill("采用第二来源，介绍留待补证");
  await page.getByRole("button", { name: "提交字段审核", exact: true }).click();
  await page.getByText("采用第二来源，介绍留待补证", { exact: true }).waitFor();
  assert.deepEqual(writes, [{ preview_token: "revision-1", note: "采用第二来源，介绍留待补证", decisions: [{ field_name: "name", action: "approve", proposal_id: "p2" }] }]);
  assert.equal(await page.getByLabel("赛事介绍的处理方式").inputValue(), "");
  assert.equal(await page.getByRole("link", { name: "查看正式详情" }).getAttribute("href"), "/competitions/3");
  await page.close();
});

// Catches treating source verification as approval and reusing stale preview tokens.
test("source verification is explicit and refreshes the preview before approval", async () => {
  let row = candidate(); const writes = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/verify")) {
      writes.push({ path: url.pathname, body: request.postDataJSON() });
      row = { ...row, preview_token: "verified-revision", fields: row.fields.map((f) => f.field_name === "description" ? { ...f, proposals: [proposal("p3", "新介绍")] } : f) };
      return { data: row };
    }
    return respondWith(() => row)(url, request);
  });
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  await page.getByLabel("赛事介绍的处理方式").selectOption("approve");
  await page.getByLabel("采用赛事介绍候选 1").check();
  await page.getByLabel("审核意见", { exact: true }).fill("已逐项核对主办方公告");
  assert.equal(await page.getByRole("button", { name: "提交字段审核", exact: true }).isDisabled(), true);
  await page.getByRole("button", { name: "核验来源 p3" }).click();
  await page.getByText("来源核验已保存", { exact: false }).waitFor();
  assert.deepEqual(writes, [{ path: "/api/admin/field-reviews/11/sources/p3/verify", body: { preview_token: "revision-1", note: "已逐项核对主办方公告" } }]);
  assert.equal(await page.getByLabel("赛事介绍的处理方式").inputValue(), "");
  await page.close();
});

// Catches silently dropping queue filters or stale detail/private drafts after identity changes.
test("all queue filters reach the API and private review content clears on account change", async () => {
  const requests = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => request.headers().authorization !== "Bearer account-A" ? { status: 403, message: "需要管理员权限" } : respondWith(candidate, requests)(url, request));
  await page.getByLabel("队列状态").selectOption("partially_approved");
  await page.getByLabel("待办标记").selectOption("CONFLICT");
  await page.getByLabel("实体类型筛选").selectOption("edition");
  await page.getByLabel("来源类型筛选").selectOption("organizer_notice");
  await page.getByLabel("赛事 ID 筛选").fill("3");
  await page.getByLabel("学校 ID 筛选").fill("8");
  await page.getByLabel("提交人 ID 筛选").fill("4");
  await page.getByLabel("提交日期从").fill("2026-09-01");
  await page.getByLabel("提交日期至").fill("2026-09-27");
  await page.getByRole("button", { name: "应用筛选" }).click();
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  const query = requests.filter((r) => r.url.pathname.endsWith("/field-reviews")).at(-1).url.searchParams;
  for (const [key, value] of Object.entries({ status: "partially_approved", flag: "CONFLICT", entity_type: "edition", source_type: "organizer_notice", competition_id: "3", university_id: "8", submitter_id: "4", created_from: "2026-09-01T00:00:00+08:00", created_to: "2026-09-27T23:59:59.999+08:00" })) assert.equal(query.get(key), value);
  await page.getByLabel("审核意见", { exact: true }).fill("PRIVATE_REVIEW_NOTE");
  await page.evaluate(() => window.changeSession("account-B"));
  await page.waitForFunction(() => !document.body.textContent.includes("秋季赛事候选") && ![...document.querySelectorAll("textarea")].some((e) => e.value.includes("PRIVATE_REVIEW_NOTE")));
  await page.getByRole("alert").first().waitFor();
  await page.close();
});

// Catches unconfirmed delete, misleading successful saves after 409, and unrestricted bulk UI.
test("delete requires confirmation and stale preview errors preserve formal data", async () => {
  const row = candidate(); row.fields = [field("description", "赛事介绍", "原介绍", null, [proposal("p4", null)], "delete")]; row.flags = [];
  const writes = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/review")) { writes.push(request.postDataJSON()); return { status: 409, message: "预览已过期，请重新加载后审核。" }; }
    return respondWith(() => row)(url, request);
  });
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  assert.equal(await page.getByRole("button", { name: "批量批准低风险字段" }).count(), 0);
  await page.getByLabel("赛事介绍的处理方式").selectOption("approve");
  await page.getByLabel("采用赛事介绍候选 1").check();
  await page.getByLabel("审核意见", { exact: true }).fill("已确认删除错误介绍");
  assert.equal(await page.getByRole("button", { name: "提交字段审核", exact: true }).isDisabled(), true);
  await page.getByLabel("确认删除赛事介绍的正式值").check();
  await page.getByRole("button", { name: "提交字段审核", exact: true }).click();
  await page.getByRole("alert").getByText("预览已过期，请重新加载后审核。", { exact: false }).waitFor();
  assert.equal(writes[0].decisions[0].confirm_delete, true);
  assert.equal(await page.getByText("原介绍", { exact: true }).count(), 1);
  await page.close();
});

// Catches candidate creation accidentally discarding alternative values or exact edition scope.
test("candidate form preserves duplicate field alternatives and explicit edition identity", async () => {
  const writes = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/field-reviews") && request.method() === "POST") { writes.push(request.postDataJSON()); return { data: { ...candidate(), entity_type: "edition", edition_id: 7, year: 2026 } }; }
    return respondWith(candidate)(url, request);
  });
  await page.getByRole("button", { name: "新建候选" }).click();
  await page.getByLabel("候选标题").fill("届次截止核对");
  await page.getByLabel("目标实体类型").selectOption("edition");
  await page.getByLabel("目标赛事 ID").fill("3");
  await page.getByLabel("目标届次 ID").fill("7");
  await page.getByLabel("届次年份").fill("2026");
  await page.getByLabel("字段 1").selectOption("registration_deadline");
  await page.getByLabel("候选值 1").fill("2026-10-01T18:00:00+08:00");
  await page.getByLabel("来源网址 1").fill("https://example.test/first");
  await page.getByRole("button", { name: "添加字段或替代来源" }).click();
  await page.getByLabel("字段 2").selectOption("registration_deadline");
  await page.getByLabel("候选值 2").fill("2026-10-02T18:00:00+08:00");
  await page.getByLabel("来源网址 2").fill("https://example.test/second");
  await page.getByRole("button", { name: "保存候选，等待审核" }).click();
  await page.getByRole("heading", { name: "秋季赛事候选" }).waitFor();
  assert.equal(writes.length, 1);
  assert.equal(writes[0].entity_type, "edition"); assert.equal(writes[0].edition_id, 7); assert.equal(writes[0].year, 2026);
  assert.deepEqual(writes[0].fields.map((f) => f.candidate_value), ["2026-10-01T18:00:00+08:00", "2026-10-02T18:00:00+08:00"]);
  await page.close();
});

// Catches follow-up review navigation reusing a previously selected candidate.
test("external conflict values remain visible and their link opens that exact candidate", async () => {
  const row = candidate(); row.fields[0].conflicts = [{ candidate_id: 12, proposal_id: "outside", candidate_value: "外部冲突值", source: source("另一份公告") }];
  const page = await mount(browser, entry, "default", {}, (url, request) => url.pathname.endsWith("/12") ? { data: { ...candidate(), id: 12, title: "另一待审候选" } } : respondWith(() => row)(url, request));
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  await page.getByText("候选 #12：外部冲突值").waitFor();
  await page.getByRole("link", { name: "查看此冲突候选" }).click();
  await page.getByRole("heading", { name: "另一待审候选" }).waitFor();
  assert.equal(await page.getByLabel("采用赛事名称候选 1").isChecked(), false);
  await page.close();
});

// Catches conflating rejection/defer with formal-field changes or selected proposals.
test("reject and defer send explicit decisions without candidate values", async () => {
  const writes = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/review")) { writes.push(request.postDataJSON()); return { data: candidate() }; }
    return respondWith(candidate)(url, request);
  });
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  await page.getByLabel("赛事名称的处理方式").selectOption("reject");
  await page.getByLabel("赛事介绍的处理方式").selectOption("defer");
  await page.getByLabel("审核意见", { exact: true }).fill("保留原名称，介绍等待更多证据");
  await page.getByRole("button", { name: "提交字段审核", exact: true }).click();
  await page.getByText("字段审核已保存；未选择的字段继续待处理。").waitFor();
  assert.deepEqual(writes[0].decisions, [{ field_name: "name", action: "reject" }, { field_name: "description", action: "defer" }]);
  await page.close();
});

// Catches batch approval adding unselected or backend-ineligible fields.
test("low-risk batch submission includes only checked fields and the current candidate", async () => {
  const row = candidate(); row.flags = []; row.fields = [field("name", "赛事名称", null, "新名称", [proposal("p1", "新名称")], "add"), field("description", "赛事介绍", null, "新介绍", [proposal("p3", "新介绍")], "add")]; row.bulk_eligible_fields = ["name", "description"];
  const writes = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/bulk-review")) { writes.push(request.postDataJSON()); return { data: [row] }; }
    return respondWith(() => row)(url, request);
  });
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  assert.equal(await page.getByRole("button", { name: "批量批准低风险字段" }).isDisabled(), true);
  await page.getByRole("checkbox", { name: "赛事介绍", exact: true }).check();
  await page.getByLabel("审核意见", { exact: true }).fill("补全已逐项核对的空缺字段");
  await page.getByRole("button", { name: "批量批准低风险字段" }).click();
  await page.getByText("选中的低风险字段已批准。").waitFor();
  assert.deepEqual(writes, [{ items: [{ id: 11, preview_token: "revision-1", field_names: ["description"] }], note: "补全已逐项核对的空缺字段" }]);
  await page.close();
});

// Catches raw-text preparation losing its original identity or using create instead of prepare.
test("free-text candidates retain their original context when structured for review", async () => {
  let row = { ...candidate(), fields: [], flags: ["NO_SOURCE"] }; const writes = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/prepare")) { writes.push({ method: request.method(), payload: request.postDataJSON() }); row = candidate(); return { data: row }; }
    return respondWith(() => row)(url, request);
  });
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  await page.getByRole("button", { name: "整理为字段候选" }).click();
  assert.equal(await page.getByLabel("原始说明").inputValue(), "人工核对候选");
  await page.getByLabel("字段 1").selectOption("name");
  await page.getByLabel("候选值 1").fill("整理后的名称");
  await page.getByRole("button", { name: "保存结构化字段，等待审核" }).click();
  await page.getByRole("heading", { name: "秋季赛事候选" }).waitFor();
  assert.equal(writes[0].method, "PUT");
  assert.equal(writes[0].payload.preview_token, "revision-1");
  assert.equal(writes[0].payload.competition_id, 3);
  assert.equal(writes[0].payload.fields[0].candidate_value, "整理后的名称");
  assert.equal(writes[0].payload.fields[0].source, undefined);
  await page.close();
});

// Catches a selected conflict alternative retaining the first proposal's misleading diff.
test("choosing a delete alternative updates the displayed candidate and change label", async () => {
  const row = candidate(); row.fields = [field("description", "赛事介绍", "原介绍", "原介绍", [proposal("p5", "原介绍"), proposal("p6", null)], "unchanged")];
  const page = await mount(browser, entry, "default", {}, respondWith(() => row));
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  await page.getByText("未变化", { exact: true }).waitFor();
  await page.getByLabel("采用赛事介绍候选 2").check();
  await page.getByText("删除", { exact: true }).waitFor();
  assert.equal(await page.getByText("原介绍", { exact: true }).count(), 1);
  await page.getByText("（空值）", { exact: true }).waitFor();
  await page.close();
});

test("unstructured evidence retains its original source and can be rejected without inventing fields", async () => {
  let row = { ...candidate(), fields: [], flags: ["NO_SOURCE"], origin_source_url: "https://example.test/original-evidence" };
  const writes = [];
  const page = await mount(browser, entry, "default", {}, (url, request) => {
    if (url.pathname.endsWith("/reject-unstructured")) {
      writes.push(request.postDataJSON()); row = { ...row, status: "rejected", preview_token: "revision-2", history: [{ action: "field_reject_unstructured", note: "材料无关，不创建任何字段", decisions: [{ action: "reject_unstructured" }] }] };
      return { data: row };
    }
    return respondWith(() => row)(url, request);
  });
  await page.getByRole("button", { name: "查看候选 秋季赛事候选" }).click();
  assert.equal(await page.getByRole("link", { name: "查看提交时的原始来源（尚未核验）" }).getAttribute("href"), row.origin_source_url);
  assert.equal(await page.getByRole("button", { name: "拒绝此原始材料", exact: true }).isDisabled(), true);
  await page.getByLabel("拒绝说明", { exact: true }).fill("材料无关，不创建任何字段");
  await page.getByRole("button", { name: "拒绝此原始材料", exact: true }).click();
  await page.getByText("原始材料已拒绝，正式数据未改变。", { exact: true }).waitFor();
  assert.deepEqual(writes, [{ preview_token: "revision-1", note: "材料无关，不创建任何字段" }]);
  assert.equal(await page.getByRole("button", { name: "整理为字段候选" }).count(), 0);
  assert.equal(await page.getByRole("button", { name: "拒绝此原始材料", exact: true }).count(), 0);
  assert.ok((await page.getByRole("region", { name: "审核历史", exact: true }).innerText()).includes("原始材料：拒绝"));
  await page.close();
});
