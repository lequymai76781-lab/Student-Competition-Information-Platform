import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { test } from "node:test";
const require = createRequire(import.meta.url);
const ts = require("typescript");

test("a selected unpublished edition remains the correction target without becoming a displayed fact", async () => {
  const code = ts.transpileModule(fs.readFileSync(new URL("../src/app/competitions/[id]/page.tsx", import.meta.url), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  const CorrectionForm = () => null;
  const api = {
    getCompetition: async () => ({ id: 3, name: "Verified Series", competition_type: "competition", current_edition_id: null, verification_status: "verified_official", editions: [], sources: [], fact_sources: [], university_notices: [], tags: [] }),
    getCompetitionRecognition: async () => [], getCompetitionUpdates: async () => [], getAllUniversities: async () => [],
  };
  vm.runInNewContext(code, { exports, require: (name) => {
    if (name === "react/jsx-runtime") return { jsx: (type, props) => ({ type, props }), jsxs: (type, props) => ({ type, props }) };
    if (name === "@/lib/api") return api;
    if (name === "@/components/v09/CorrectionForm") return { CorrectionForm };
    if (name === "@/lib/format") return new Proxy({}, { get: () => () => "unknown" });
    return {};
  } });
  const tree = await exports.default({ params: { id: "3" }, searchParams: { edition_id: "17" } });
  function find(node) {
    if (!node || typeof node !== "object") return null;
    if (node.type === CorrectionForm) return node;
    for (const child of Array.isArray(node) ? node : [node.props?.children]) { const match = find(child); if (match) return match; }
    return null;
  }
  assert.equal(find(tree)?.props.editionId, 17);
});
