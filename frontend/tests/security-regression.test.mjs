import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import { chromium, mount, projectStyles } from "./browser-harness.mjs";

let browser;
before(async () => { browser = await chromium.launch({ headless: true, channel: "msedge" }); });
after(async () => { await browser?.close(); });
const row = (id, description = `record-${id}`) => ({ id, title: description, description, status: "pending", kind: "other", created_at: "2026-09-27T00:00:00Z", competition_id: 1, correction_type: "其他", editions: [] });
const overview = { profile_complete: true, profile: { user_id: 1, email: "a@test.invalid", university_name: "A_PRIVATE_SCHOOL" }, counts: {}, now_available: [], upcoming_deadline: [], direction_related: [], school_notices: [], college_notices: [], school_directory: [], college_directory: [], favorites: [], status_views: {} };

test("mobile app shell exposes logout and clears private records when clicked", async () => {
  const page = await mount(browser, "src/components/v09/ContributionHistory.tsx", "ContributionHistory", {}, (url) => url.pathname.endsWith("unread-count") ? { unread: 1 } : [row(1, "A_PRIVATE_RECORD")], { wrapShell: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.addStyleTag({ content: await projectStyles() });
  await page.getByText("A_PRIVATE_RECORD", { exact: true }).first().waitFor();
  const logout = page.getByRole("button", { name: "退出", includeHidden: true }).first();
  assert.equal(await logout.isVisible(), true);
  await logout.click();
  await page.waitForFunction(() => !document.body.textContent.includes("A_PRIVATE_RECORD"));
  assert.equal(await page.evaluate(() => localStorage.getItem("v09_token")), null);
  await page.close();
});

for (const entry of ["admin/review", "notifications", "settings/profile", "onboarding"]) test(`${entry} restores a stored session during SSR hydration without redirecting to login`, async () => {
  const page = await mount(browser, `src/app/${entry}/page.tsx`, "default", {}, (url) => {
    if (url.pathname.endsWith("/summary")) return {};
    if (url.pathname.endsWith("/auth/me")) return { user: overview.profile, onboarding_complete: false };
    if (url.pathname.endsWith("/notifications")) return { items: [], unread: 0 };
    return [];
  }, { hydrate: true });
  await page.waitForFunction(() => document.body.textContent.length > 30);
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await page.evaluate(() => window.testRoutes.includes("/login")), false);
  await page.close();
});

test("login rejects controls, encoded authority changes and external URLs while retaining internal query/hash", async () => {
  const page = await mount(browser, "src/app/login/page.tsx", "default", {}, () => ({ token: "login-token", onboarding_complete: true, user: overview.profile }));
  for (const [next, expected] of [
    ["/\t/evil.example", "/my-competitions"], ["/%09/evil.example", "/my-competitions"],
    ["/%2509/evil.example", "/my-competitions"], ["/%2f/evil.example", "/my-competitions"],
    ["/%255cevil.example", "/my-competitions"], ["/\r/evil.example", "/my-competitions"],
    ["/\n/evil.example", "/my-competitions"], ["https://evil.example", "/my-competitions"],
    ["//evil.example", "/my-competitions"], ["javascript:alert(1)", "/my-competitions"],
    ["data:text/html,evil", "/my-competitions"], ["/\\evil.example", "/my-competitions"],
    ["//trusted.example@evil.example/", "/my-competitions"], ["https%3A%2F%2Fevil.example", "/my-competitions"],
    ["%252F%252Fevil.example", "/my-competitions"], ["/safe/..//evil.example", "/my-competitions"],
    ["/competitions/42?q=hello%20world#source", "/competitions/42?q=hello%20world#source"],
    ["/my%20competitions?return=https%3A%2F%2Fexample.test#section", "/my%20competitions?return=https%3A%2F%2Fexample.test#section"],
  ]) {
    await page.evaluate((value) => history.replaceState(null, "", `/?next=${encodeURIComponent(value)}`), next);
    await page.getByLabel("邮箱").fill("a@test.invalid");
    await page.locator('input[type="password"]').fill("secretpass");
    await page.getByRole("button", { name: "登录", exact: true }).click();
    await page.waitForFunction(() => window.testRoutes.length > 0);
    assert.equal(await page.evaluate(() => window.testRoutes.pop()), expected, JSON.stringify(next));
  }
  await page.close();
});

test("contribution rows disappear immediately when identity changes and B fails", async () => {
  const page = await mount(browser, "src/components/v09/ContributionHistory.tsx", "ContributionHistory", {}, (url, request) => request.headers().authorization === "Bearer account-A" ? [row(1, "A_PRIVATE_RECORD")] : { status: 503 });
  await page.getByText("A_PRIVATE_RECORD", { exact: true }).first().waitFor();
  await page.evaluate(() => window.changeSession("account-B"));
  await page.waitForFunction(() => !document.body.textContent.includes("A_PRIVATE_RECORD"));
  await page.getByRole("alert").first().waitFor();
  assert.equal(await page.getByText("A_PRIVATE_RECORD", { exact: true }).count(), 0);
  await page.close();
});

test("an A response arriving after B loaded cannot replace B private rows", async () => {
  const waiting = [];
  let started;
  const allStarted = new Promise((resolve) => { started = resolve; });
  const page = await mount(browser, "src/components/v09/ContributionHistory.tsx", "ContributionHistory", {}, (_, request) => {
    if (request.headers().authorization === "Bearer account-A") return new Promise((resolve) => {
      waiting.push(resolve); if (waiting.length === 2) started();
    });
    return [row(2, "B_PRIVATE_RECORD")];
  });
  await allStarted;
  await page.evaluate(() => window.changeSession("account-B"));
  await page.getByText("B_PRIVATE_RECORD", { exact: true }).first().waitFor();
  waiting.forEach((resolve) => resolve([row(1, "A_PRIVATE_RECORD")]));
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await page.getByText("A_PRIVATE_RECORD", { exact: true }).count(), 0);
  assert.ok(await page.getByText("B_PRIVATE_RECORD", { exact: true }).count() > 0);
  await page.close();
});

for (const nextToken of [null, "account-A-refreshed"]) test(`contribution draft and results reset on ${nextToken ? "token refresh" : "logout"}`, async () => {
  const page = await mount(browser, "src/components/v09/CorrectionForm.tsx", "CorrectionForm", {}, () => ({}));
  await page.getByLabel("学校、专业或赛事名称").fill("A_PRIVATE_DRAFT");
  await page.getByLabel("具体说明").fill("A_PRIVATE_DESCRIPTION");
  await page.evaluate((value) => window.changeSession(value), nextToken);
  await page.waitForFunction(() => ![...document.querySelectorAll("input,textarea")].some((el) => el.value.includes("A_PRIVATE")));
  if (nextToken) assert.equal(await page.getByLabel("学校、专业或赛事名称").inputValue(), "");
  else await page.getByRole("link", { name: "登录后提交补充" }).waitFor();
  await page.close();
});

test("personal calendar clears its expanded private events on logout", async () => {
  const page = await mount(browser, "src/components/v09/PersonalCalendar.tsx", "PersonalCalendar", {}, () => [{ competition_id: 1, name: "A_PRIVATE_CALENDAR", deadline: "2026-10-01T00:00:00Z", deadline_label: "报名截止" }]);
  await page.getByRole("button", { name: "查看 1 个" }).click();
  await page.getByText("A_PRIVATE_CALENDAR").waitFor();
  await page.evaluate(() => window.changeSession(null));
  await page.waitForFunction(() => !document.body.textContent.includes("A_PRIVATE_CALENDAR"));
  await page.close();
});

for (const [entry, name, aData, privateText] of [
  ["src/components/v09/PersonalHome.tsx", "PersonalHome", overview, "A_PRIVATE_SCHOOL"],
  ["src/app/my-competitions/page.tsx", "default", overview, "A_PRIVATE_SCHOOL"],
  ["src/app/settings/profile/page.tsx", "default", { user: overview.profile }, "A_PRIVATE_SCHOOL"],
  ["src/app/notifications/page.tsx", "default", { items: [{ ...row(1), title: "A_PRIVATE_NOTICE", is_read: false }], unread: 7 }, "A_PRIVATE_NOTICE"],
  ["src/app/admin/review/page.tsx", "default", [row(1, "A_PRIVATE_REVIEW")], "A_PRIVATE_REVIEW"],
  ["src/components/v09/PersonalContext.tsx", "PersonalContext", { found: true, item: { competition_id: 1, name: "Contest", reasons: [{ type: "school", text: "A_PRIVATE_CONTEXT" }], effective_deadline: "2026-10-01T00:00:00Z" } }, "A_PRIVATE_CONTEXT"],
  ["src/components/v09/NotificationBell.tsx", "NotificationBell", { unread: 87 }, "87"],
  ["src/app/onboarding/page.tsx", "default", { user: overview.profile, onboarding_complete: false }, "A_PRIVATE_SCHOOL"],
]) test(`${entry} clears old private content on account change and failed load`, async () => {
  const page = await mount(browser, entry, name, { competitionId: 1, editionId: 7, universityId: 8, collegeId: 9 }, async (url, request) => {
    if (request.headers().authorization !== "Bearer account-A") {
      await new Promise((resolve) => setTimeout(resolve, 700));
      return { status: 403, message: "需要管理员权限" };
    }
    if (url.pathname.endsWith("/notifications")) return entry.includes("notifications") ? aData : { items: [], unread: 0 };
    if (url.pathname.endsWith("/summary")) return {};
    if (url.pathname.includes("/directory/") || url.pathname.includes("/universities")) return [];
    return aData;
  });
  await page.waitForFunction((text) => document.body.textContent.includes(text) || [...document.querySelectorAll("input")].some((el) => el.value.includes(text)), privateText);
  await page.evaluate(() => window.changeSession("account-B"));
  await page.waitForFunction((text) => !document.body.textContent.includes(text) && ![...document.querySelectorAll("input")].some((el) => el.value.includes(text)), privateText, { timeout: 400 });
  await page.close();
});

test("both personal histories reach record 51 using independent bounded pagination", async () => {
  const requests = [];
  const page = await mount(browser, "src/components/v09/ContributionHistory.tsx", "ContributionHistory", {}, (url) => {
    requests.push(url);
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 50);
    return Array.from({ length: 51 }, (_, i) => row(i + 1)).slice(offset, offset + limit);
  });
  const supplementSection = page.getByRole("region", { name: "我的信息补充" });
  await supplementSection.waitFor({ timeout: 1200 });
  await supplementSection.getByRole("button", { name: "下一页" }).click();
  await supplementSection.getByText("record-21", { exact: true }).first().waitFor();
  await supplementSection.getByRole("button", { name: "下一页" }).click();
  await supplementSection.getByText("record-51", { exact: true }).first().waitFor();
  assert.ok(requests.every((url) => Number(url.searchParams.get("limit")) <= 100 && Number(url.searchParams.get("limit")) > 0));
  const corrections = page.getByRole("region", { name: "我的纠错" });
  await corrections.getByText("record-1", { exact: true }).first().waitFor();
  assert.equal(await supplementSection.getByRole("button", { name: "下一页" }).isDisabled(), true);
  await corrections.getByRole("button", { name: "下一页" }).click();
  await corrections.getByText("record-21", { exact: true }).first().waitFor();
  await corrections.getByRole("button", { name: "下一页" }).click();
  await corrections.getByText("record-51", { exact: true }).first().waitFor();
  assert.equal(await corrections.getByRole("button", { name: "下一页" }).isDisabled(), true);
  await page.close();
});

test("admin can reach needs_more_evidence and record 51 in the supplement queue", async () => {
  const page = await mount(browser, "src/app/admin/review/page.tsx", "default", {}, (url) => {
    if (url.pathname.endsWith("summary")) return {};
    const offset = Number(url.searchParams.get("offset") ?? 0);
    const limit = Number(url.searchParams.get("limit") ?? 50);
    if (url.pathname.endsWith("corrections")) return url.searchParams.get("status") === "needs_more_evidence" ? [row(99, "NEEDS_EVIDENCE_REVIEW")] : [];
    return url.pathname.endsWith("supplements") ? Array.from({ length: 51 }, (_, i) => row(i + 1)).slice(offset, offset + limit) : [];
  });
  await page.getByLabel("审核状态").waitFor({ timeout: 1200 });
  await page.getByLabel("审核状态").selectOption("needs_more_evidence");
  await page.getByText("NEEDS_EVIDENCE_REVIEW", { exact: true }).waitFor();
  await page.getByRole("button", { name: "信息补充", exact: true }).click();
  await page.getByText("record-1", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "下一页" }).click();
  await page.getByText("record-21", { exact: true }).first().waitFor();
  await page.getByRole("button", { name: "下一页" }).click();
  await page.getByText("record-51", { exact: true }).first().waitFor();
  await page.close();
});
