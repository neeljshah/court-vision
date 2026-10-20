// a11y-gate.mjs -- axe-core over the exported site in both themes; fails on any
// serious or critical violation (the WCAG A/AA floor: contrast, names, roles,
// keyboard reachability). Moderate/minor findings are printed as warnings so
// they stay visible without blocking.
//
//   node scripts/a11y-gate.mjs [outDir=out] [pagesFile=perf/a11y-pages.json]
//
// Needs a Chromium: in CI the runner's Google Chrome (playwright-core
// channel "chrome"); locally set A11Y_CHROME=/path/to/chrome or install Chrome.
import { readFileSync } from "node:fs";
import { chromium } from "playwright-core";
import AxeBuilder from "@axe-core/playwright";
import { createServer } from "./serve-export.mjs";
import { resolvePage, readManifest } from "./perf-pages.mjs";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];
const BLOCKING = new Set(["serious", "critical"]);

/** Splits axe violations into blocking (serious/critical) and advisory sets. Exported for the test. */
export function triage(violations) {
  const blocking = [], advisory = [];
  for (const v of violations) (BLOCKING.has(v.impact) ? blocking : advisory).push({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help, targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) });
  return { blocking, advisory };
}

export function formatViolation(page, theme, v) {
  return `${page} [${theme}] ${v.id} (${v.impact}) x${v.nodes}: ${v.help} -- ${v.targets.join(" | ")}`;
}

async function launch() {
  const executablePath = process.env.A11Y_CHROME;
  if (executablePath) return chromium.launch({ executablePath, args: ["--no-sandbox"] });
  try {
    return await chromium.launch({ channel: "chrome", args: ["--no-sandbox"] });
  } catch (err) {
    throw new Error(`a11y-gate: no Chrome found (${err.message.split("\n")[0]}); set A11Y_CHROME=/path/to/chrome`);
  }
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain) {
  const outDir = process.argv[2] || "out";
  const config = JSON.parse(readFileSync(process.argv[3] || "perf/a11y-pages.json", "utf8"));
  const manifest = readManifest();
  config.pages = config.pages.map((entry) => resolvePage(entry, manifest)).filter(Boolean);
  const server = createServer(outDir, config.basePath);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}${config.basePath}`;
  const browser = await launch();
  let blockingCount = 0, advisoryCount = 0;
  try {
    for (const page of config.pages) {
      for (const theme of ["dark", "light"]) {
        const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
        await ctx.addInitScript((t) => { try { localStorage.setItem("cv-theme", t); localStorage.setItem("cv-analytics-theme", t); } catch {} }, theme);
        const pg = await ctx.newPage();
        const resp = await pg.goto(base + page, { waitUntil: "networkidle" });
        if (!resp || resp.status() !== 200) { console.error(`::error::${page}: HTTP ${resp ? resp.status() : "no response"}`); blockingCount += 1; await ctx.close(); continue; }
        await pg.waitForTimeout(400);
        const results = await new AxeBuilder({ page: pg }).withTags(TAGS).analyze();
        const { blocking, advisory } = triage(results.violations);
        for (const v of blocking) console.error(`::error::${formatViolation(page, theme, v)}`);
        for (const v of advisory) console.warn(`::warning::${formatViolation(page, theme, v)}`);
        blockingCount += blocking.length; advisoryCount += advisory.length;
        console.log(`${page} [${theme}] blocking ${blocking.length}, advisory ${advisory.length}`);
        await ctx.close();
      }
    }
  } finally {
    await browser.close();
    server.close();
  }
  if (blockingCount) { console.error(`\na11y-gate: ${blockingCount} serious/critical violation(s)`); process.exit(1); }
  console.log(`\na11y-gate GREEN: zero serious/critical axe violations on ${config.pages.length} pages x 2 themes (${advisoryCount} advisory).`);
}
