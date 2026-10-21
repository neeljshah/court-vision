// crawl-export.mjs -- link crawl over the static export. Walks every out/**/*.html,
// pulls every href / src (plus a stub's meta refresh url), resolves each one the way
// GitHub Pages serves the project site (basePath, one percent-decode, directory
// index.html) and reports: internal targets missing from out/ (a 404 on Pages),
// links that land on a retired-route stub (with the final target from lib/redirects.ts),
// internal links without the trailing slash (a Pages redirect hop), anchors whose id is
// absent on the target page, and the external hosts referenced. Exits non-zero ONLY for
// missing internal targets; everything else is a report. ASCII only.
//
//   node scripts/crawl-export.mjs [outDir=out] [basePath=/court-vision] [--top=30]
//
// Output: a Markdown table per page family, the top offending (page, href) pairs, the
// offending hrefs by how many pages carry them (a template defect shows up here), the
// external hosts, and a ```json blob the workflow extracts into the crawl-report artifact.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { classify, extractIds, extractRefs, familyOf, hostKind, pagePath, readRedirects } from "./crawl-links.mjs";

export const ORIGIN = "https://neeljshah.github.io";
const SEVERITY = { missing: 0, stub: 1, noSlash: 2, badAnchor: 3 };

/** Every file under dir as a posix-relative path. */
export function walk(dir, root = dir, out = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full, root, out);
    else out.push(relative(root, full).split(sep).join("/"));
  }
  return out;
}

/**
 * Crawl an export. `redirects` is { stubs, prefixStubs } (readRedirects). Returns the
 * per-family rows, the offending (page, href) pairs, the per-href aggregate, the external
 * hosts and the totals; the CLI below prints them.
 */
export function crawl(outDir, basePath, redirects, { origin = ORIGIN, top = 30 } = {}) {
  const files = new Set(walk(outDir));
  const idCache = new Map();
  const ids = (rel) => {
    if (!idCache.has(rel)) idCache.set(rel, extractIds(readFileSync(join(outDir, rel), "utf8")));
    return idCache.get(rel);
  };
  const ctx = { basePath, origin, files, ids, ...redirects };
  const families = new Map();
  const pairs = new Map();      // "page\thref" -> offence
  const byHref = new Map();     // href -> { problem, detail, pages:Set }
  const hosts = new Map();      // host -> { kind, tags:{tag:count}, pages:Set }
  const addPair = (page, href, problem, detail) => {
    const key = `${page}\t${href}`;
    if (!pairs.has(key)) pairs.set(key, { page, href, problem, detail });
    const agg = byHref.get(`${problem}\t${href}`) || { href, problem, detail, pages: new Set() };
    agg.pages.add(page);
    byHref.set(`${problem}\t${href}`, agg);
  };
  const pages = [...files].filter((f) => f.endsWith(".html")).sort();
  for (const rel of pages) {
    const page = pagePath(rel);
    const fam = familyOf(page);
    const row = families.get(fam) || { family: fam, pages: 0, links: 0, missing: 0, stub: 0, noSlash: 0, badAnchor: 0, hosts: new Set() };
    row.pages += 1;
    const html = readFileSync(join(outDir, rel), "utf8");
    idCache.set(rel, extractIds(html));
    for (const ref of extractRefs(html)) {
      const r = classify(ref, page, ctx);
      if (r.kind === "skip") continue;
      row.links += 1;
      if (r.kind === "external") {
        const h = hosts.get(r.host) || { host: r.host, kind: hostKind(r.host), tags: {}, pages: new Set() };
        h.tags[ref.tag] = (h.tags[ref.tag] || 0) + 1;
        h.pages.add(page);
        hosts.set(r.host, h);
        row.hosts.add(r.host);
        continue;
      }
      if (r.kind === "missing" || r.kind === "malformed") {
        row.missing += 1;
        addPair(page, ref.value, "missing", r.detail || "malformed url");
        continue;
      }
      if (r.stub) { row.stub += 1; addPair(page, ref.value, "stub", `stub ${r.path} -> ${r.stub}`); }
      if (r.noSlash) { row.noSlash += 1; addPair(page, ref.value, "noSlash", `serves ${r.target} after a redirect hop`); }
      if (r.badAnchor) { row.badAnchor += 1; addPair(page, ref.value, "badAnchor", `no id "${r.badAnchor}" on ${r.target}`); }
    }
    families.set(fam, row);
  }
  const rows = [...families.values()].sort((a, b) => a.family.localeCompare(b.family))
    .map((r) => ({ ...r, hosts: [...r.hosts].sort() }));
  const offenders = [...pairs.values()]
    .sort((a, b) => SEVERITY[a.problem] - SEVERITY[b.problem] || a.page.localeCompare(b.page) || a.href.localeCompare(b.href));
  const hrefs = [...byHref.values()].map((a) => ({ ...a, pages: a.pages.size, example: [...a.pages].sort()[0] }))
    .sort((a, b) => SEVERITY[a.problem] - SEVERITY[b.problem] || b.pages - a.pages || a.href.localeCompare(b.href));
  const external = [...hosts.values()].map((h) => ({ ...h, pages: h.pages.size })).sort((a, b) => b.pages - a.pages);
  const totals = rows.reduce((t, r) => ({ pages: t.pages + r.pages, links: t.links + r.links, missing: t.missing + r.missing,
    stub: t.stub + r.stub, noSlash: t.noSlash + r.noSlash, badAnchor: t.badAnchor + r.badAnchor }),
  { pages: 0, links: 0, missing: 0, stub: 0, noSlash: 0, badAnchor: 0 });
  return { rows, offenders: offenders.slice(0, top), offenderCount: offenders.length, hrefs: hrefs.slice(0, top), external, totals };
}

const cell = (s) => String(s).replace(/\|/g, "\\|");

export function formatReport(res) {
  const L = [];
  L.push("| family | pages | links | missing | stub | no slash | bad anchor | external hosts |");
  L.push("|---|---:|---:|---:|---:|---:|---:|---|");
  for (const r of res.rows) L.push(`| ${r.family} | ${r.pages} | ${r.links} | ${r.missing} | ${r.stub} | ${r.noSlash} | ${r.badAnchor} | ${cell(r.hosts.join(", ")) || "-"} |`);
  const t = res.totals;
  L.push(`| **total** | ${t.pages} | ${t.links} | ${t.missing} | ${t.stub} | ${t.noSlash} | ${t.badAnchor} | ${res.external.length} |`);
  L.push("", `Top ${res.offenders.length} of ${res.offenderCount} offending (page, href) pairs:`, "");
  L.push("| page | href | problem | detail |", "|---|---|---|---|");
  for (const o of res.offenders) L.push(`| ${cell(o.page)} | ${cell(o.href)} | ${o.problem} | ${cell(o.detail)} |`);
  if (!res.offenders.length) L.push("| - | - | none | - |");
  L.push("", "Offending hrefs by the number of pages that carry them (a template defect ranks first):", "");
  L.push("| href | problem | pages | example page | detail |", "|---|---|---:|---|---|");
  for (const h of res.hrefs) L.push(`| ${cell(h.href)} | ${h.problem} | ${h.pages} | ${cell(h.example)} | ${cell(h.detail)} |`);
  if (!res.hrefs.length) L.push("| - | none | 0 | - | - |");
  L.push("", "External hosts (an <a> is a navigation only; link / script / img are requests the page makes):", "");
  L.push("| host | kind | tags | pages |", "|---|---|---|---:|");
  for (const h of res.external) L.push(`| ${h.host} | ${h.kind} | ${Object.entries(h.tags).map(([k, v]) => `${k} x${v}`).join(", ")} | ${h.pages} |`);
  if (!res.external.length) L.push("| - | - | - | 0 |");
  return L.join("\n");
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split(/[\\/]/).pop());
if (isMain) {
  const args = process.argv.slice(2);
  const topArg = args.find((a) => a.startsWith("--top="));
  const pos = args.filter((a) => !a.startsWith("--"));
  const outDir = pos[0] || "out";
  const basePath = pos[1] || "/court-vision";
  const res = crawl(outDir, basePath, readRedirects(), { top: topArg ? Number(topArg.slice(6)) || 30 : 30 });
  console.log(`crawl-export: ${res.totals.pages} pages, ${res.totals.links} internal/external refs checked under ${basePath}\n`);
  console.log(formatReport(res));
  const { rows, offenders, hrefs, external, totals } = res;
  console.log("\n```json\n" + JSON.stringify({ basePath, totals, rows, offenders, hrefs, external }) + "\n```");
  if (totals.missing) {
    console.error(`\ncrawl-export: ${totals.missing} internal reference(s) have no target in ${outDir} (404 on Pages)`);
    process.exit(1);
  }
  console.log(`\ncrawl-export GREEN: every internal reference resolves (${totals.stub} stub landing(s), ${totals.noSlash} without the trailing slash, ${totals.badAnchor} bad anchor(s) reported above).`);
}
