#!/usr/bin/env node

// Verify the small, public analytics surface after `next build`.
// This intentionally uses Node built-ins so it can run before any extra CI
// tooling is installed and on both Windows and Linux runners.

import { gzipSync } from "node:zlib";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
let OUT = resolve(process.argv[2] || join(HERE, "..", "out"));
let BASE_PATH = normalizeBase(process.env.NEXT_PUBLIC_BASE_PATH || "/court-vision");
const REQUIRED_ROUTES = [
  "/analytics/",
  "/analytics/ask/",
  "/analytics/lab/",
  "/analytics/compare/",
  "/analytics/evidence/",
  "/analytics/browse/",
  "/analytics/state-reliability/",
  "/analytics/pitch-sequencing/",
  "/analytics/count-context/",
  "/analytics/score-decomposition/",
  "/analytics/observation-dependence/",
  "/analytics/residual-anatomy/",
  "/analytics/blowout-timing/",
  "/analytics/state-contrasts/",
  "/analytics/cross-sport-comparability/",
  "/analytics/papers/",
];
const BUDGETS = new Map([
  ["/analytics/", 200_000],
  ["/analytics/lab/", 400_000],
  ["/analytics/compare/", 400_000],
  ["/analytics/ask/", 500_000],
  ["/analytics/evidence/", 100_000],
  ["/analytics/browse/", 100_000],
]);
const ASSET_EXTENSIONS = /\.(?:json|png|jpe?g|webp|gif|svg|avif|ico)$/i;

function normalizeBase(value) {
  const clean = String(value || "").trim();
  if (!clean || clean === "/") return "";
  return `/${clean.replace(/^\/+|\/+$/g, "")}`;
}

function htmlEntities(value) {
  return value
    .replace(/&amp;/gi, "&")
    .replace(/&#38;/gi, "&")
    .replace(/&#x26;/gi, "&");
}

function safePath(value) {
  return String(value).replace(/[^\x20-\x7e]/g, "?");
}

function routeFile(route) {
  const path = routePath(route);
  if (path === null) return null;
  const decoded = decodePath(path);
  if (decoded === null || decoded.includes("\0")) return null;
  const rel = decoded.replace(/^\/+/, "");
  const candidates = decoded.endsWith("/")
    ? [join(OUT, rel, "index.html")]
    : [join(OUT, rel), join(OUT, rel, "index.html"), join(OUT, `${rel}.html`)];
  return candidates.find((candidate) => isInsideOut(candidate) && existsSync(candidate)) || null;
}

function isInsideOut(candidate) {
  const out = resolve(OUT);
  const target = resolve(candidate);
  return target === out || target.startsWith(`${out}${sep}`);
}

function decodePath(path) {
  try {
    return decodeURIComponent(path);
  } catch {
    return null;
  }
}

function routePath(route) {
  const raw = htmlEntities(route.trim());
  if (!raw || raw.startsWith("#") || raw.startsWith("?") || raw.startsWith("//")) return null;
  let parsed;
  try {
    parsed = new URL(raw, "https://courtvision.invalid/");
  } catch {
    return null;
  }
  if (parsed.origin !== "https://courtvision.invalid") return null;
  let path = parsed.pathname || "/";
  if (BASE_PATH) {
    if (path === BASE_PATH) path = "/";
    else if (path.startsWith(`${BASE_PATH}/`)) path = path.slice(BASE_PATH.length);
  }
  return path || "/";
}

function sourceUrl(sourceFile) {
  const rel = relative(OUT, sourceFile).split(sep).join("/");
  if (rel === "index.html") return "/";
  if (rel.endsWith("/index.html")) return `/${rel.slice(0, -"index.html".length)}`;
  return `/${rel}`;
}

function routeLabel(sourceFile) {
  return sourceUrl(sourceFile) || "/";
}

function isExternal(raw) {
  const value = raw.trim().toLowerCase();
  return value.startsWith("//") || /^(?:data|blob|mailto|tel|javascript):/.test(value);
}

function references(html) {
  const found = [];
  const attr = /\b(?:href|src)\s*=\s*["']([^"']*)["']/gi;
  for (const match of html.matchAll(attr)) found.push(match[1]);
  const srcset = /\bsrcset\s*=\s*["']([^"']*)["']/gi;
  for (const match of html.matchAll(srcset)) {
    for (const item of match[1].split(",")) found.push(item.trim().split(/\s+/)[0]);
  }
  return found;
}

function targetForReference(raw, sourceFile) {
  const value = htmlEntities(String(raw || "").trim());
  if (!value || value.startsWith("#") || value.startsWith("?") || isExternal(value)) return null;
  let parsed;
  try {
    parsed = new URL(value, `https://courtvision.invalid${sourceUrl(sourceFile)}`);
  } catch {
    return { malformed: true };
  }
  if (parsed.origin !== "https://courtvision.invalid") return null;
  const path = parsed.pathname || "/";
  // A rooted link must carry basePath in a Pages export. This catches raw
  // <a href="/analytics/..."> links that work locally but 404 on the project site.
  if (BASE_PATH && value.startsWith("/") && path !== BASE_PATH && !path.startsWith(`${BASE_PATH}/`)) {
    return { missingBase: true, path };
  }
  const normalized = routePath(`${path}${parsed.search}`);
  return normalized === null ? { malformed: true } : { path: normalized };
}

function verifyReferences(sourceFile, html, failures) {
  for (const raw of references(html)) {
    const target = targetForReference(raw, sourceFile);
    if (!target) continue;
    if (target.malformed) {
      failures.push(`${routeLabel(sourceFile)} has an invalid internal reference`);
      continue;
    }
    if (target.missingBase) {
      failures.push(`${routeLabel(sourceFile)} is missing basePath for ${safePath(target.path)}`);
      continue;
    }
    const file = routeFile(target.path);
    if (!file) {
      const kind = ASSET_EXTENSIONS.test(target.path) ? "asset" : "route or asset";
      failures.push(`${routeLabel(sourceFile)} references missing ${kind} ${safePath(target.path)}`);
    }
  }
}

function verifyBudget(route, maxBytes, failures) {
  const file = routeFile(route);
  if (!file) return;
  const bytes = gzipSync(readFileSync(file)).length;
  const kb = (bytes / 1024).toFixed(1);
  const maxKb = (maxBytes / 1024).toFixed(0);
  if (bytes >= maxBytes) failures.push(`${route} gzip HTML is ${kb} KB (limit ${maxKb} KB)`);
  else return;
}

function analyticsHtmlFiles() {
  const files = [];
  function visit(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) visit(path);
      else if (entry.isFile() && entry.name.endsWith(".html")) files.push(path);
    }
  }
  const root = join(OUT, "analytics");
  if (existsSync(root)) visit(root);
  return files;
}

export function webpInfo(file) {
  const bytes = readFileSync(file);
  if (bytes.toString("ascii", 0, 4) !== "RIFF" || bytes.toString("ascii", 8, 12) !== "WEBP") return null;
  const chunk = bytes.toString("ascii", 12, 16);
  if (chunk === "VP8L" && bytes.length >= 25 && bytes[20] === 0x2f) {
    const bits = bytes[21] | (bytes[22] << 8) | (bytes[23] << 16) | (bytes[24] << 24);
    return { alpha: Boolean((bits >>> 28) & 1), width: (bits & 0x3fff) + 1, height: ((bits >>> 14) & 0x3fff) + 1 };
  }
  if (chunk !== "VP8X" || bytes.length < 30) return null;
  return {
    alpha: (bytes[20] & 0x10) !== 0,
    width: 1 + bytes[24] + (bytes[25] << 8) + (bytes[26] << 16),
    height: 1 + bytes[27] + (bytes[28] << 8) + (bytes[29] << 16),
  };
}

export function verifyExport(out, basePath = BASE_PATH) {
  const failures = [];
  // Keep the full scan behind one entry point so CI and focused tests agree.
  OUT = resolve(out);
  BASE_PATH = normalizeBase(basePath);
  const searchIndexFile = join(OUT, "analytics", "search-index.json");
  let records = [];
  if (!existsSync(searchIndexFile)) failures.push("required analytics search index is missing");
  else {
    try {
      const parsed = JSON.parse(readFileSync(searchIndexFile, "utf8"));
      records = Array.isArray(parsed.records) ? parsed.records : [];
    }
    catch { failures.push("analytics search index is invalid JSON"); }
  }
  const derived = records.filter((record) => String(record?.id || "").startsWith("research-") && record.href);
  if (derived.length < 33) failures.push("search index is missing derived analyses");
  const indexedRoutes = new Set(records.map((record) => record?.href).filter(Boolean).map((href) => `${href.replace(/\/$/, "")}/`));
  const requiredRoutes = [...new Set([...REQUIRED_ROUTES, ...derived.map((record) => `${record.href.replace(/\/$/, "")}/`)])];
  const sitemapFile = join(OUT, "sitemap.xml");
  const sitemap = existsSync(sitemapFile) ? readFileSync(sitemapFile, "utf8") : "";
  for (const route of new Set([...requiredRoutes, ...indexedRoutes])) if (!sitemap.includes(`${BASE_PATH}${route}</loc>`)) failures.push(`sitemap is missing ${route}`);
  for (const route of indexedRoutes) if (!routeFile(route)) failures.push(`search index references missing route ${safePath(route)}`);
  for (const route of requiredRoutes) if (!routeFile(route)) failures.push(`required route missing ${route}`);
  const htmlFiles = analyticsHtmlFiles();
  let referenceCount = 0;
  for (const file of htmlFiles) {
    const html = readFileSync(file, "utf8");
    referenceCount += references(html).length;
    verifyReferences(file, html, failures);
  }
  const emblem = join(OUT, "brand", "courtvision-emblem.webp");
  const info = existsSync(emblem) ? webpInfo(emblem) : null;
  if (!info) failures.push("generated analytics emblem is missing or not a readable WebP");
  else if (!info.alpha || info.width !== 1254 || info.height !== 1254) failures.push(`generated analytics emblem must be 1254x1254 with alpha (got ${info.width}x${info.height}, alpha ${info.alpha})`);
  const manifestFile = join(OUT, "manifest.webmanifest");
  if (existsSync(manifestFile)) {
    try {
      const manifest = JSON.parse(readFileSync(manifestFile, "utf8"));
      if (![`${BASE_PATH}/games`, `${BASE_PATH}/games/`].includes(manifest.start_url)) failures.push(`manifest start_url is not base-prefixed (${safePath(manifest.start_url || "missing")})`);
      if (manifest.scope !== `${BASE_PATH}/`) failures.push(`manifest scope is not base-prefixed (${safePath(manifest.scope || "missing")})`);
    } catch { failures.push("manifest.webmanifest is invalid JSON"); }
  }
  const budgets = new Map(BUDGETS);
  for (const route of derived.map((record) => `${record.href.replace(/\/$/, "")}/`)) budgets.set(route, 150_000);
  for (const [route, maxBytes] of budgets) verifyBudget(route, maxBytes, failures);
  return { failures, htmlCount: htmlFiles.length, indexedCount: indexedRoutes.size, referenceCount, checkedRoutes: requiredRoutes.length };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = verifyExport(OUT);
  console.log(`Analytics export scan: ${result.htmlCount} HTML routes, ${result.indexedCount} search destinations, ${result.referenceCount} references.`);
  if (result.failures.length) {
    console.error(`Analytics export verification failed (${result.failures.length} issue${result.failures.length === 1 ? "" : "s"}):`);
    for (const failure of result.failures.slice(0, 25)) console.error(`- ${safePath(failure)}`);
    if (result.failures.length > 25) console.error(`- ... ${result.failures.length - 25} additional issue${result.failures.length === 26 ? "" : "s"}`);
    process.exitCode = 1;
  } else console.log(`Analytics export verification passed (basePath ${BASE_PATH || "/"}).`);
}
