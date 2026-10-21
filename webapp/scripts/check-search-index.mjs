#!/usr/bin/env node
// check-search-index.mjs -- crawl the exported command-palette index and prove
// every result resolves in the export: each record href must map to an exported
// HTML page under out/, none may be a redirect stub (meta refresh), ids must be
// unique, and the site pages the palette promises must be present.
//
//   node scripts/check-search-index.mjs [outDir=out]
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const REQUIRED_PAGES = [
  "/", "/games", "/desk", "/desk/health", "/paper-trading", "/evidence", "/evidence/retractions",
  "/receipts", "/about", "/how-it-works", "/methodology", "/graveyard",
];

/** Exported file for a basePath-free href, or null when the export has none. */
export function exportedFile(outDir, href) {
  const path = href.split(/[?#]/)[0].replace(/\/+$/, "");
  const candidates = path === "" ? [join(outDir, "index.html")] : [join(outDir, path, "index.html"), join(outDir, `${path}.html`)];
  return candidates.find((file) => existsSync(file)) || null;
}

export function isRedirectStub(html) {
  return /<meta[^>]+http-equiv=["']refresh["']/i.test(html);
}

/** Returns the list of failures (empty when the index is sound). */
export function checkIndex(outDir, records) {
  const failures = [];
  const ids = new Set();
  for (const record of records) {
    if (ids.has(record.id)) failures.push(`duplicate id ${record.id}`);
    ids.add(record.id);
    if (typeof record.href !== "string" || !record.href.startsWith("/")) { failures.push(`${record.id}: href is not a site path`); continue; }
    const file = exportedFile(outDir, record.href);
    if (!file) { failures.push(`${record.id}: ${record.href} is not in the export`); continue; }
    if (isRedirectStub(readFileSync(file, "utf8"))) failures.push(`${record.id}: ${record.href} is a redirect stub`);
  }
  const hrefs = new Set(records.map((record) => String(record.href).replace(/\/+$/, "") || "/"));
  for (const page of REQUIRED_PAGES) if (!hrefs.has(page)) failures.push(`site page missing from the index: ${page}`);
  return failures;
}

function main() {
  const outDir = resolve(process.argv[2] || join(HERE, "..", "out"));
  const indexFile = join(outDir, "analytics", "search-index.json");
  if (!existsSync(indexFile)) { console.error(`search index not exported: ${indexFile}`); process.exit(1); }
  const { records } = JSON.parse(readFileSync(indexFile, "utf8"));
  const failures = checkIndex(outDir, records);
  const counts = records.reduce((acc, record) => ({ ...acc, [record.type]: (acc[record.type] || 0) + 1 }), {});
  console.log(`search index: ${records.length} records (${Object.entries(counts).map(([type, n]) => `${n} ${type}`).join(", ")})`);
  if (failures.length) { failures.forEach((failure) => console.error(`  FAIL ${failure}`)); process.exit(1); }
  console.log("search index GREEN: every href resolves to an exported page, none is a redirect stub, all required site pages present.");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
