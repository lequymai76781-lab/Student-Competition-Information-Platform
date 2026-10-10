import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { test } from "node:test";

const require = createRequire(import.meta.url);
const ts = require("typescript");
process.env.TZ = "UTC";
function load(file, context = {}) {
  const source = fs.readFileSync(new URL(`../src/lib/${file}.ts`, import.meta.url), "utf8");
  const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const exports = {};
  vm.runInNewContext(code, { exports, process, URL, URLSearchParams, Event, ...context });
  return exports;
}
function apiHarness() {
  let stored = "A";
  let finish;
  const api = load("v09-api", { window: { localStorage: { getItem: () => stored, setItem: (_, value) => { stored = value; }, removeItem: () => { stored = null; } }, dispatchEvent() {} }, fetch: () => new Promise((resolve) => { finish = resolve; }) });
  return { api, stored: () => stored, respond: (status, data = {}) => finish({ ok: status === 200, status, json: async () => status === 200 ? { data } : { message: "failed" } }) };
}

test("401 expires only its originating current token", async () => {
  const h = apiHarness();
  const request = h.api.me();
  h.respond(401);
  await assert.rejects(request);
  assert.equal(h.stored(), null);
});
test("late A 401 does not clear the newly active B token", async () => {
  const h = apiHarness();
  const request = h.api.me();
  h.api.setToken("B");
  h.respond(401);
  await assert.rejects(request);
  assert.equal(h.stored(), "B");
});
test("late successful private response from A is discarded after B login", async () => {
  const h = apiHarness();
  const request = h.api.myCorrections();
  h.api.setToken("B");
  h.respond(200, [{ description: "A_PRIVATE_RECORD" }]);
  await assert.rejects(request);
});
test("identity is rechecked after a delayed response body finishes parsing", async () => {
  let stored = "A";
  let finishBody;
  const api = load("v09-api", {
    window: { localStorage: { getItem: () => stored }, dispatchEvent() {} },
    fetch: async () => ({ ok: true, status: 200, json: () => new Promise((resolve) => { finishBody = resolve; }) }),
  });
  const request = api.myCorrections();
  await new Promise((resolve) => setImmediate(resolve));
  stored = "B";
  finishBody({ data: [{ description: "PRIVATE_A" }] });
  await assert.rejects(request);
});
test("403 refuses data while preserving the current session", async () => {
  const h = apiHarness();
  const request = h.api.adminCorrections();
  h.respond(403);
  await assert.rejects(request);
  assert.equal(h.stored(), "A");
});
test("personal context preserves the explicit edition and school scope", async () => {
  let requested;
  const api = load("v09-api", { fetch: async (url) => { requested = new URL(url); return { ok: true, json: async () => ({ data: { found: true } }) }; } });
  await api.competitionContext(3, { edition_id: 17, university_id: 8, college_id: 9 });
  assert.equal(requested.pathname, "/api/users/me/competitions/3/context");
  assert.equal(requested.searchParams.get("edition_id"), "17");
  assert.equal(requested.searchParams.get("university_id"), "8");
  assert.equal(requested.searchParams.get("college_id"), "9");
});
test("expired instants are labeled expired, even by less than a day", () => {
  const format = load("format", { Date: class extends Date { static now() { return Date.parse("2026-09-27T12:00:00Z"); } } });
  assert.equal(format.daysUntil("2026-09-27T11:59:59Z"), "已截止");
});
test("date display consistently uses the Shanghai business day", () => {
  assert.equal(load("format").formatDate("2026-09-27T17:00:00Z"), "2026/09/28");
});

test("atomic review errors preserve safe structured failure context without private fields", async () => {
  const api = load("v09-api", { fetch: async () => ({ ok: false, status: 409, json: async () => ({ detail: { message: "审核预览已失效", failed_candidate_id: 121, succeeded: 0, failed: 2, pending_ids: [101, 121], stack: "PRIVATE_STACK", secret: "PRIVATE_SECRET" } }) }) });
  await assert.rejects(api.apiFetch("/admin/field-reviews/bulk-review"), (error) => {
    assert.ok(error.message.includes("审核预览已失效"));
    assert.ok(error.message.includes("#121") && error.message.includes("0"));
    assert.equal(error.status, 409);
    assert.equal(error.reviewFailure.failed_candidate_id, 121);
    assert.deepEqual(Array.from(error.reviewFailure.pending_ids), [101, 121]);
    assert.equal(JSON.stringify(error).includes("PRIVATE_"), false);
    return true;
  });
});
// Per-request audit binding must survive transport without overriding current-account auth.
test("business audit session header survives while caller cannot replace authorization", async () => {
  let observed;
  const api = load("v09-api", { Headers, window: { localStorage: { getItem: () => "current-admin" } }, fetch: async (_url, init) => { observed = new Headers(init.headers); return { ok: true, json: async () => ({ data: {} }) }; } });
  await api.apiFetch("/admin/field-reviews/11/review", { headers: { "X-Review-Learning-Session": "session-11", authorization: "Bearer other-admin" } });
  assert.equal(observed.get("X-Review-Learning-Session"), "session-11");
  assert.equal(observed.get("Authorization"), "Bearer current-admin");
});
