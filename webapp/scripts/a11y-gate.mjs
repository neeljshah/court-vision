// a11y-gate.mjs -- axe-core over the exported site in both themes; fails on any
// serious or critical violation (the WCAG A/AA floor: contrast, names, roles,
// keyboard reachability). Moderate/minor findings are printed as warnings so
// they stay visible without blocking.
//
//   node scripts/a11y-gate.mjs [outDir=out] [pagesFile=perf/a11y-pages.json] [--report]
//   --report: print per-page/theme counts + violations and a JSON blob, never fail.
//
// Needs a Chromium: in CI the runner's Google Chrome (playwright-core
// channel "chrome"); locally set A11Y_CHROME=/path/to/chrome or install Chrome
// (the launcher is shared with keyboard-walk and third-party-requests: scripts/browser.mjs).
import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { createServer } from "./serve-export.mjs";
import { resolvePage, readManifest } from "./perf-pages.mjs";
import { launchChrome } from "./browser.mjs";

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];
const BLOCKING = new Set(["serious", "critical"]);

/** Splits axe violations into blocking (serious/critical) and advisory sets. Exported for the test. */
export function triage(violations) {
  const blocking = [], advisory = [];
  for (const v of violations) (BLOCKING.has(v.impact) ? blocking : advisory).push({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help, targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) });
  return { blocking, advisory };
}

/** Report-mode row: counts per impact for one page/theme. Exported for the test. */
export function countByImpact(violations) {
  const c = { critical: 0, serious: 0, moderate: 0, minor: 0 };
  for (const v of violations) if (v.impact in c) c[v.impact] += 1;
  return c;
}

export function formatViolation(page, theme, v) {
  return `${page} [${theme}] ${v.id} (${v.impact}) x${v.nodes}: ${v.help} -- ${v.targets.join(" | ")}`;
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain) {
  const report = process.argv.includes("--report");
  const args = process.argv.slice(2).filter((a) => a !== "--report");
  const outDir = args[0] || "out";
  const config = JSON.parse(readFileSync(args[1] || "perf/a11y-pages.json", "utf8"));
  const rows = [], summary = [];
  const manifest = readManifest();
  config.pages = config.pages.map((entry) => resolvePage(entry, manifest)).filter(Boolean);
  const server = createServer(outDir, config.basePath);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const base = `http://127.0.0.1:${server.address().port}${config.basePath}`;
  let browser;
  try { browser = await launchChrome("a11y-gate"); } catch (err) {
    if (!report) throw err;
    console.log(`a11y report skipped: ${err.message}`); server.close(); process.exit(0);
  }
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
        if (report) {
          rows.push({ page, theme, ...countByImpact(results.violations) });
          for (const v of [...blocking, ...advisory]) summary.push(formatViolation(page, theme, v));
          await ctx.close(); continue;
        }
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
  if (report) {
    console.log("| page | theme | critical | serious | moderate | minor |\n|---|---|---|---|---|---|");
    for (const r of rows) console.log(`| ${r.page} | ${r.theme} | ${r.critical} | ${r.serious} | ${r.moderate} | ${r.minor} |`);
    console.log("\nViolations:\n" + (summary.join("\n") || "none"));
    console.log("\n```json\n" + JSON.stringify({ rows, violations: summary }) + "\n```");
    process.exit(0);
  }
  if (blockingCount) { console.error(`\na11y-gate: ${blockingCount} serious/critical violation(s)`); process.exit(1); }
  console.log(`\na11y-gate GREEN: zero serious/critical axe violations on ${config.pages.length} pages x 2 themes (${advisoryCount} advisory).`);
}
