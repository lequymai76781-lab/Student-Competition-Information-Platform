import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const require = createRequire(path.join(root, "package.json"));
const ts = require("typescript");
export const { chromium } = require("playwright");

// Bundle the installed React runtime and actual TS components. Only Next navigation,
// icons, and the HTTP boundary are replaced; hooks and DOM reconciliation are real.
export function bundle(entry, exportName = "default", props = {}, hydrate = false, wrapShell = false) {
  const modules = new Map();
  const stubs = {
    "next/link": "module.exports = function Link(props) { return require('react').createElement('a', props); };",
    "next/navigation": "exports.useRouter = () => window.testRouter; exports.usePathname = () => window.location.pathname;",
    "lucide-react": "module.exports = new Proxy({}, {get: () => () => null});",
  };
  function add(file) {
    if (modules.has(file)) return;
    modules.set(file, "");
    const source = stubs[file] ?? fs.readFileSync(file, "utf8");
    let code = file.endsWith(".ts") || file.endsWith(".tsx")
      ? ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText
      : source;
    code = code.replace(/require\(["']([^"']+)["']\)/g, (_, name) => {
      let resolved;
      if (name in stubs) resolved = name;
      else if (name.startsWith("@/")) {
        const candidate = path.join(root, "src", name.slice(2));
        resolved = [candidate, `${candidate}.ts`, `${candidate}.tsx`].find((item) => fs.existsSync(item));
      } else resolved = createRequire(file in stubs ? path.join(root, "package.json") : file).resolve(name);
      add(resolved);
      return `require(${JSON.stringify(resolved)})`;
    });
    modules.set(file, code);
  }
  const file = path.join(root, entry);
  const react = require.resolve("react");
  const client = require.resolve("react-dom/client");
  const server = hydrate ? require.resolve("react-dom/server.browser") : null;
  const shell = wrapShell ? path.join(root, "src/components/AppShell.tsx") : null;
  add(file); add(react); add(client);
  if (server) add(server);
  if (shell) add(shell);
  return `const process = {env:{NODE_ENV:'development',NEXT_PUBLIC_API_BASE_URL:'http://app.test/api'}};
  const modules = {${[...modules].map(([id, code]) => `${JSON.stringify(id)}:function(module,exports,require){${code}\n}`).join(",")}};
  const cache={}; function require(id){if(!cache[id]){const module={exports:{}};cache[id]=module;modules[id](module,module.exports,require);}return cache[id].exports;}
  window.testRoutes=[]; window.testRouter={push:(url)=>window.testRoutes.push(url),replace:(url)=>window.testRoutes.push(url),refresh:()=>{}};
  window.changeSession=(value)=>{value?localStorage.setItem('v09_token',value):localStorage.removeItem('v09_token');window.dispatchEvent(new Event('storage'));};
  localStorage.setItem('v09_token','account-A');
  const React=require(${JSON.stringify(react)});const element=React.createElement(require(${JSON.stringify(file)})[${JSON.stringify(exportName)}],${JSON.stringify(props)});
  const tree=${wrapShell ? `React.createElement(require(${JSON.stringify(shell)}).AppShell, {children:element})` : "element"};
  ${hydrate ? `document.getElementById('root').innerHTML=require(${JSON.stringify(server)}).renderToString(tree);require(${JSON.stringify(client)}).hydrateRoot(document.getElementById('root'),tree);` : `require(${JSON.stringify(client)}).createRoot(document.getElementById('root')).render(tree);`}`;
}

export async function projectStyles() {
  const config = require("tailwindcss/loadConfig")(path.join(root, "tailwind.config.ts"));
  config.content = [path.join(root, "src/**/*.{ts,tsx}")];
  const result = await require("postcss")([require("tailwindcss")(config)]).process("@tailwind utilities;", { from: undefined });
  return result.css;
}

export async function mount(browser, entry, exportName, props, respond, { hydrate = false, wrapShell = false } = {}) {
  const page = await browser.newPage();
  page.setDefaultTimeout(2500);
  await page.route("http://app.test/**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith("/api/")) {
      const result = await respond(url, route.request());
      await route.fulfill({ status: result?.status ?? 200, contentType: "application/json", body: JSON.stringify(result?.status ? { message: result.message ?? "request failed" } : { data: result?.data ?? result }) });
    } else await route.fulfill({ contentType: "text/html", body: '<div id="root"></div>' });
  });
  await page.goto("http://app.test/");
  await page.addScriptTag({ content: bundle(entry, exportName, props, hydrate, wrapShell) });
  return page;
}
