#!/usr/bin/env node
// meta-audit.mjs -- audit the exported HTML head of every page family (print only, never fails).
//
// Usage:
//   node scripts/meta-audit.mjs [outDir=out] [--report] [--json] [--verbose]
//   --report  Markdown tables + a JSON block (what the webapp QA workflow appends to its summary).
//   --json    the JSON summary alone.
//   --verbose list every offending page path under the tables.
//
// Checks per out/**/index.html: a non-empty <title> that is not the bare site name, a
// <meta name="description"> under 160 characters that is unique inside its family, a
// <link rel="canonical"> equal to the page's own trailing-slash URL (a redirect stub may
// point at its destination; a noindex 404 needs none), og:title / og:description that are the
// page's own (not the root layout's generic card), og:url, twitter:card summary_large_image,
// for redirect stubs a robots noindex beside the meta refresh, and no retracted figure in any
// meta text. JSON-LD scripts are counted per family.
// Node built-ins only (no DOM parser): the head is a flat list of tags, so regexes do.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve, sep } from "node:path";

export const SITE_NAME = "CourtVision";
export const DESCRIPTION_MAX = 160;
const ORIGIN = process.env.NEXT_PUBLIC_SITE_URL || "https://neeljshah.github.io";
const BASE = (process.env.NEXT_PUBLIC_BASE_PATH || "/court-vision").replace(/\/+$/, "");

/** Page family from the basePath-free route (trailing slash). */
export function familyOf(route, { refresh = false } = {}) {
  if (refresh) return "stub";
  if (route === "/") return "home";
  const m = route.match(/^\/(analytics\/(?:players\/[^/]+|m|research|papers|findings|explainers)|evidence|paper|receipts|games\/[^/]+)\/[^/]+\/$/);
  if (m) {
    const head = m[1];
    if (head.startsWith("analytics/players/")) return "players";
    if (head.startsWith("games/")) return "games";
    if (head.startsWith("analytics/")) return head.slice("analytics/".length);
    return head;
  }
  return route.startsWith("/analytics/") ? "analytics" : "site";
}

const attr = (tag, name) => {
  const m = tag.match(new RegExp(`\\s${name}\\s*=\\s*("([^"]*)"|'([^']*)')`, "i"));
  return m ? (m[2] ?? m[3] ?? "") : null;
};
const decode = (s) => s.replace(/&quot;/g, '"').replace(/&#x27;|&#39;/g, "'").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");

/** Parse the head tags this audit cares about out of one HTML document. */
export function parseHead(html) {
  const head = (html.match(/<head[^>]*>([\s\S]*?)<\/head>/i) || [, html])[1];
  const metas = [...head.matchAll(/<meta\b[^>]*>/gi)].map((m) => m[0]);
  const links = [...head.matchAll(/<link\b[^>]*>/gi)].map((m) => m[0]);
  const meta = (key, value) => {
    const tag = metas.find((t) => (attr(t, key) || "").toLowerCase() === value);
    return tag ? decode(attr(tag, "content") || "") : null;
  };
  const canonicalTag = links.find((t) => (attr(t, "rel") || "").toLowerCase() === "canonical");
  const title = head.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const refresh = metas.some((t) => (attr(t, "http-equiv") || "").toLowerCase() === "refresh")
    || /<meta\b[^>]*http-equiv="refresh"/i.test(html);
  return {
    title: title ? decode(title[1].trim()) : null,
    description: meta("name", "description"),
    canonical: canonicalTag ? decode(attr(canonicalTag, "href") || "") : null,
    ogTitle: meta("property", "og:title"),
    ogDescription: meta("property", "og:description"),
    ogUrl: meta("property", "og:url"),
    twitterCard: meta("name", "twitter:card"),
    robots: meta("name", "robots"),
    refresh,
    jsonLd: (html.match(/<script[^>]*type="application\/ld\+json"/gi) || []).length,
  };
}

const decodeAll = (s) => { let cur = s; for (let i = 0; i < 3 && cur.includes("%"); i++) { try { const n = decodeURIComponent(cur); if (n === cur) break; cur = n; } catch { break; } } return cur; };
const samePage = (canonical, route) => decodeAll(canonical) === decodeAll(`${ORIGIN}${BASE}${route}`);
export const RETRACTED_TOKENS = ["+18.38%", "0.119", "+54%", "78.11", "8.94", "54.57"];

/** Audit one page; returns the list of check names it fails. */
export function auditPage(route, parsed) {
  const fails = [];
  if (!parsed.title || parsed.title.trim() === SITE_NAME) fails.push("title");
  if (parsed.description == null || !parsed.description.trim()) fails.push("description");
  else if (parsed.description.length >= DESCRIPTION_MAX) fails.push("description-long");
  // A noindex page that is not a redirect stub (the 404) has no URL of its own: no canonical, no og:url.
  const unlisted = /noindex/i.test(parsed.robots || "") && !parsed.refresh;
  if (!parsed.canonical) { if (!unlisted) fails.push("canonical"); }
  else if (parsed.refresh ? !parsed.canonical.startsWith(`${ORIGIN}${BASE}/`) : !samePage(parsed.canonical, route)) fails.push("canonical-wrong");
  // og:title / og:description inherited from the root layout read as the generic site card on every page.
  if (!parsed.ogTitle || (route !== "/" && parsed.ogTitle === SITE_NAME)) fails.push("og:title");
  if (!parsed.ogDescription || (route !== "/" && parsed.description && parsed.ogDescription !== parsed.description)) fails.push("og:description");
  if (!parsed.ogUrl && !unlisted) fails.push("og:url");
  if (parsed.twitterCard !== "summary_large_image") fails.push("twitter:card");
  if (parsed.refresh && !/noindex/i.test(parsed.robots || "")) fails.push("noindex");
  const meta = `${parsed.title} ${parsed.description} ${parsed.ogDescription}`;
  if (RETRACTED_TOKENS.some((t) => meta.includes(t))) fails.push("retracted-token");
  return fails;
}

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) yield* walk(p);
    else if (name === "index.html") yield p;
  }
}

// Read every index.html under outDir into { route, family, parsed, fails }.
export function auditExport(outDir) {
  const pages = [];
  for (const file of walk(outDir)) {
    const rel = relative(outDir, file).split(sep).slice(0, -1).join("/");
    const route = rel ? `/${rel}/` : "/";
    const parsed = parseHead(readFileSync(file, "utf-8"));
    pages.push({ route, family: familyOf(route, { refresh: parsed.refresh }), parsed, fails: auditPage(route, parsed) });
  }
  return pages.sort((a, b) => a.route.localeCompare(b.route));
}

const CHECKS = ["title", "description", "description-long", "canonical", "canonical-wrong", "og:title", "og:description", "og:url", "twitter:card", "noindex", "retracted-token"];
const FAMILY_ORDER = ["home", "site", "stub", "analytics", "players", "m", "research", "papers", "findings", "explainers", "evidence", "paper", "receipts", "games"];

/** Per-family counts, including descriptions duplicated inside the family. */
export function summarize(pages) {
  const byFamily = new Map();
  for (const p of pages) {
    if (!byFamily.has(p.family)) byFamily.set(p.family, []);
    byFamily.get(p.family).push(p);
  }
  const families = [...byFamily.keys()].sort((a, b) => (FAMILY_ORDER.indexOf(a) + 99) % 99 - (FAMILY_ORDER.indexOf(b) + 99) % 99 || a.localeCompare(b));
  const rows = families.map((family) => {
    const list = byFamily.get(family);
    const counts = Object.fromEntries(CHECKS.map((c) => [c, list.filter((p) => p.fails.includes(c)).length]));
    const seen = new Map();
    for (const p of list) if (p.parsed.description) seen.set(p.parsed.description, (seen.get(p.parsed.description) || 0) + 1);
    const duplicates = list.filter((p) => p.parsed.description && seen.get(p.parsed.description) > 1);
    for (const p of duplicates) p.fails.push("description-duplicate");
    return { family, pages: list.length, duplicateDescription: duplicates.length, jsonLd: list.filter((p) => p.parsed.jsonLd > 0).length, ...counts };
  });
  const total = { family: "total", pages: pages.length };
  for (const key of ["duplicateDescription", "jsonLd", ...CHECKS]) total[key] = rows.reduce((n, r) => n + r[key], 0);
  return { rows, total };
}

const cell = (n) => (n ? String(n) : "0");
const line = (r) => `| ${r.family} | ${r.pages} | ${cell(r.title)} | ${cell(r.duplicateDescription)} | ${cell(r.canonical)} |`;
const detail = (r) => `| ${r.family} | ${cell(r.description)} | ${cell(r["description-long"])} | ${cell(r["canonical-wrong"])} | ${cell(r["og:title"])} | ${cell(r["og:description"])} | ${cell(r["og:url"])} | ${cell(r["twitter:card"])} | ${cell(r.noindex)} | ${cell(r["retracted-token"])} | ${cell(r.jsonLd)} |`;

export function renderMarkdown(summary, pages, { verbose = false } = {}) {
  const out = ["## Metadata audit", "", "| family | pages | missing title | duplicate description | missing canonical |", "|---|---:|---:|---:|---:|"];
  for (const r of summary.rows) out.push(line(r));
  out.push(line(summary.total), "");
  out.push("| family | missing description | description >= 160 | wrong canonical | generic or missing og:title | og:description not the page's | missing og:url | twitter:card not summary_large_image | stub without noindex | retracted token in meta | pages with JSON-LD |");
  out.push("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|");
  for (const r of summary.rows) out.push(detail(r));
  out.push(detail(summary.total), "");
  if (verbose) {
    const bad = pages.filter((p) => p.fails.length);
    out.push(`### Pages with findings (${bad.length})`, "");
    for (const p of bad) out.push(`- ${p.route}: ${p.fails.join(", ")}`);
    out.push("");
  }
  return out.join("\n");
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain) {
  const flags = new Set(process.argv.slice(2).filter((a) => a.startsWith("--")));
  const outDir = resolve(process.argv.slice(2).find((a) => !a.startsWith("--")) || "out");
  if (!existsSync(outDir)) {
    console.log(`meta-audit: ${outDir} does not exist (run the static export first); nothing audited.`);
    process.exit(0);
  }
  const pages = auditExport(outDir);
  const summary = summarize(pages);
  const json = { outDir: relative(process.cwd(), outDir) || ".", origin: ORIGIN, basePath: BASE, ...summary,
    offenders: pages.filter((p) => p.fails.length).map((p) => ({ route: p.route, family: p.family, fails: p.fails })) };
  if (flags.has("--json")) console.log(JSON.stringify(json, null, 2));
  else {
    console.log(renderMarkdown(summary, pages, { verbose: flags.has("--verbose") }));
    if (flags.has("--report")) console.log("```json\n" + JSON.stringify(json) + "\n```");
  }
  console.log(`meta-audit: ${pages.length} pages, ${json.offenders.length} with findings (report only; never fails the build).`);
}
