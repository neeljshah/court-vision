// perf-budget.mjs -- static performance budget for the exported site (no browser).
//
// Reads webapp/perf/budget.json and, for every page listed there, parses the
// exported index.html, resolves the <script src> (module scripts only; the
// noModule polyfill is never fetched by a modern browser) and stylesheet
// <link>s, and compares the gzip size of the HTML, the JS and the CSS against
// the page's ceilings. Also caps image files under public/ so an unoptimised
// re-staged chart or icon cannot slip back in. Exits 1 on any breach.
//
//   node scripts/perf-budget.mjs [outDir=out] [budgetFile=perf/budget.json] [--report]
//   --report: print a Markdown table + JSON of every measurement, never fail.
//
// Ceilings are set from perf/AFTER_2026-10-20.md with ~10% headroom; raise one
// only with a perf/ note that says what the bytes buy.
import { readFileSync, existsSync, statSync, readdirSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join, extname } from "node:path";
import { resolvePage, readManifest } from "./perf-pages.mjs";

export function gzipBytes(buf) {
  return gzipSync(buf, { level: 6 }).length;
}

/** Script and stylesheet URLs referenced by one exported page. */
export function pageAssets(html) {
  const clean = html.replace(/\\u002F/g, "/");
  const scripts = [];
  for (const m of clean.matchAll(/<script([^>]*)>/g)) {
    if (/\bnomodule\b/i.test(m[1])) continue;
    const src = m[1].match(/\bsrc="([^"]+)"/);
    if (src && !scripts.includes(src[1])) scripts.push(src[1]);
  }
  const styles = [];
  for (const m of clean.matchAll(/<link([^>]*)>/g)) {
    if (!/rel="stylesheet"/.test(m[1])) continue;
    const href = m[1].match(/\bhref="([^"]+)"/);
    if (href && !styles.includes(href[1])) styles.push(href[1]);
  }
  return { scripts, styles };
}

function localPath(outDir, basePath, url) {
  // Next percent-encodes dynamic segments in chunk URLs ("[id]" -> "%5Bid%5D");
  // the file on disk keeps the brackets.
  const decoded = decodeURIComponent(url);
  const rel = decoded.startsWith(basePath + "/") ? decoded.slice(basePath.length) : decoded;
  return join(outDir, rel);
}

/** Measures one page: gzip bytes of HTML, JS and CSS plus the resolved file lists. */
export function measurePage(outDir, basePath, page) {
  const file = join(outDir, decodeURIComponent(page).replace(/^\//, ""), "index.html");
  if (!existsSync(file)) return { page, missing: true };
  const html = readFileSync(file);
  const { scripts, styles } = pageAssets(html.toString("utf8"));
  const sum = (urls) => urls.reduce((acc, u) => {
    const p = localPath(outDir, basePath, u);
    if (!existsSync(p)) { acc.missing.push(u); return acc; }
    const buf = readFileSync(p);
    acc.raw += buf.length; acc.gz += gzipBytes(buf);
    return acc;
  }, { raw: 0, gz: 0, missing: [] });
  const js = sum(scripts), css = sum(styles);
  return { page, htmlGz: gzipBytes(html), htmlRaw: html.length, jsGz: js.gz, jsRaw: js.raw, cssGz: css.gz, cssRaw: css.raw,
    jsFiles: scripts.length, cssFiles: styles.length, missing: [...js.missing, ...css.missing] };
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) walk(p, out); else out.push(p);
  }
  return out;
}

/** Image files over their directory's ceiling. */
export function oversizedImages(publicDir, caps) {
  const hits = [];
  for (const [subdir, cap] of Object.entries(caps)) {
    const dir = join(publicDir, subdir);
    if (!existsSync(dir)) continue;
    for (const f of walk(dir)) {
      if (![".png", ".webp", ".jpg", ".jpeg", ".avif", ".gif"].includes(extname(f).toLowerCase())) continue;
      const size = statSync(f).size;
      if (size > cap.maxBytes && !(cap.exempt || []).some((name) => f.endsWith(name))) hits.push({ file: f, size, cap: cap.maxBytes });
    }
  }
  return hits;
}

/** Runs every budget; returns the list of failures (empty = green) and the measurements. */
export function checkBudget(budget, outDir, publicDir, manifest = null) {
  const failures = [];
  const rows = [];
  for (const [entry, limits] of Object.entries(budget.pages)) {
    const page = resolvePage(entry, manifest);
    if (!page) { failures.push(`${entry}: cannot be resolved from the demo manifest`); continue; }
    const m = measurePage(outDir, budget.basePath, page);
    m.entry = entry;
    rows.push(m);
    if (m.missing === true) { failures.push(`${page}: not exported`); continue; }
    if (m.missing.length) failures.push(`${page}: referenced assets missing from export: ${m.missing.join(", ")}`);
    for (const [key, label] of [["jsGz", "JS"], ["cssGz", "CSS"], ["htmlGz", "HTML"]]) {
      if (limits[key] != null && m[key] > limits[key]) failures.push(`${page}: ${label} ${m[key]} bytes gzip exceeds budget ${limits[key]}`);
    }
  }
  for (const hit of oversizedImages(publicDir, budget.images || {})) {
    failures.push(`${hit.file}: ${hit.size} bytes exceeds image cap ${hit.cap}`);
  }
  return { failures, rows };
}

/** Report mode: measures every page in the budget file (and every image) with no pass/fail. */
export function reportBudget(budget, outDir, publicDir, manifest = null) {
  const pages = [];
  for (const entry of Object.keys(budget.pages)) {
    const page = resolvePage(entry, manifest);
    if (!page) { pages.push({ page: entry, missing: true }); continue; }
    const m = measurePage(outDir, budget.basePath, page);
    pages.push(m.missing === true ? { page, missing: true } : { page, htmlGz: m.htmlGz, jsGz: m.jsGz, cssGz: m.cssGz, jsFiles: m.jsFiles, cssFiles: m.cssFiles });
  }
  const images = [];
  for (const subdir of Object.keys(budget.images || {})) {
    const dir = join(publicDir, subdir);
    if (!existsSync(dir)) continue;
    for (const f of walk(dir)) {
      if ([".png", ".webp", ".jpg", ".jpeg", ".avif", ".gif"].includes(extname(f).toLowerCase())) images.push({ file: f.split("\\").join("/"), size: statSync(f).size });
    }
  }
  images.sort((a, b) => b.size - a.size);
  return { pages, images };
}

export function reportMarkdown({ pages, images }) {
  const kb = (n) => (n / 1024).toFixed(1);
  const lines = ["| page | html gz KB | js gz KB | css gz KB | js files |", "|---|---|---|---|---|"];
  for (const r of pages) lines.push(r.missing ? `| ${r.page} | not exported | | | |` : `| ${r.page} | ${kb(r.htmlGz)} | ${kb(r.jsGz)} | ${kb(r.cssGz)} | ${r.jsFiles} |`);
  lines.push("", "| largest images | KB |", "|---|---|");
  for (const i of images.slice(0, 10)) lines.push(`| ${i.file} | ${kb(i.size)} |`);
  return lines.join("\n");
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain) {
  const args = process.argv.slice(2).filter((a) => a !== "--report");
  const outDir = args[0] || "out";
  const budgetFile = args[1] || "perf/budget.json";
  const budget = JSON.parse(readFileSync(budgetFile, "utf8"));
  if (process.argv.includes("--report")) {
    const report = reportBudget(budget, outDir, "public", readManifest());
    console.log(reportMarkdown(report));
    console.log("\n```json\n" + JSON.stringify(report) + "\n```");
    process.exit(0);
  }
  const { failures, rows } = checkBudget(budget, outDir, "public", readManifest());
  for (const r of rows) {
    if (r.missing === true) continue;
    const lim = budget.pages[r.entry];
    console.log(`${r.page}  html ${r.htmlGz}/${lim.htmlGz ?? "-"}  js ${r.jsGz}/${lim.jsGz ?? "-"}  css ${r.cssGz}/${lim.cssGz ?? "-"}  (gzip bytes, measured/budget)`);
  }
  if (failures.length) {
    console.error(`\nperf-budget: ${failures.length} breach(es)`);
    for (const f of failures) console.error(`::error::${f}`);
    process.exit(1);
  }
  console.log("\nperf-budget GREEN: every page is within its JS/CSS/HTML budget and no image exceeds its cap.");
}
