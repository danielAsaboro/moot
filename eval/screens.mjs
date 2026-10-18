// README screenshots of the live app, taken with Playwright (Chromium) against https://moot.bringaihome.xyz.
//   node eval/screens.mjs [base-url]      writes docs/screens/*.png
// Needs the `playwright` package, resolved from NODE_PATH if set (it is not a dependency of the app).
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const { chromium } = createRequire(process.env.NODE_PATH ? join(process.env.NODE_PATH, "_") : import.meta.url)("playwright");
const BASE = process.argv[2] || "https://moot.bringaihome.xyz";
const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "docs", "screens");
mkdirSync(OUT, { recursive: true });

const shots = [
  { name: "landing", idle: false, path: "/", wait: 6000 },
  { name: "judges", idle: false, path: "/#judges", wait: 4000, then: async p => { await p.evaluate(() => document.getElementById("judges")?.scrollIntoView()); await p.waitForTimeout(800); } },
  { name: "k8s-ledger", path: "/app/ledger/?graph=gh_kubernetes_enhancements", wait: 5000 },
  { name: "k8s-kep", path: "/app/ledger/?graph=gh_kubernetes_enhancements&d=KEP-3130", wait: 5000 },
  { name: "evidence-path", path: "/app/?d=D01&tab=graph", wait: 5000, scroll: 330 },
  { name: "cypher", path: "/app/?d=D01", wait: 3000, scroll: 420,
    then: async p => { await p.getByRole("tab", { name: "Cypher" }).or(p.getByRole("button", { name: "Cypher", exact: true })).first().click(); await p.waitForTimeout(1500); } },
  { name: "people", path: "/app/people/", wait: 4000 },
  { name: "graph-picker", path: "/app/ledger/?graph=gh_alphagov_govuk_infrastructure", wait: 8000,
    then: async p => { await p.getByRole("button", { name: /^Graph:/ }).click(); await p.waitForTimeout(1200); } },
  { name: "stated-reason", idle: false, path: "/app/?graph=gh_thomvaill_log4brains&d=20200925-multi-packages-architecture-in-a-monorepo-with-yarn-and-lerna", wait: 4000,
    then: async p => { const row = p.getByRole("button", { name: /Yarn and Lerna are considered/ }).first(); await row.scrollIntoViewIfNeeded(); await row.click();
      await p.waitForTimeout(800); await p.evaluate(() => window.scrollBy(0, 420)); await p.waitForTimeout(400); } },
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 2, colorScheme: "light", reducedMotion: "reduce" });
for (const s of shots) {
  if (process.env.ONLY && !process.env.ONLY.split(",").includes(s.name)) continue;
  const p = await ctx.newPage();
  await p.goto(BASE + s.path, { waitUntil: s.idle === false ? "load" : "networkidle", timeout: 90000 });
  await p.waitForTimeout(s.wait);
  if (s.then) await s.then(p);
  if (s.scroll) { await p.mouse.wheel(0, s.scroll); await p.waitForTimeout(800); }
  await p.screenshot({ path: join(OUT, `${s.name}.png`) });
  console.log("wrote", s.name);
  await p.close();
}
await browser.close();
