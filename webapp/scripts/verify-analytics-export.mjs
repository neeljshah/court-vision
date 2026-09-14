#!/usr/bin/env node

// Verify the small, public analytics surface after `next build`.
// This intentionally uses Node built-ins so it can run before any extra CI
// tooling is installed and on both Windows and Linux runners.

import { gzipSync } from "node:zlib";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(process.argv[2] || join(HERE, "..", "out"));
const BASE_PATH = normalizeBase(process.env.NEXT_PUBLIC_BASE_PATH || "/court-vision");
const REQUIRED_ROUTES = [
  "/analytics/",
  "/analytics/ask/",
  "/analytics/lab/",
  "/analytics/compare/",
  "/analytics/evidence/",
];
const BUDGETS = new Map([
  ["/analytics/", 200_000],
  ["/analytics/lab/", 400_000],
  ["/analytics/compare/", 400_000],
  ["/analytics/ask/", 500_000],
  ["/analytics/evidence/", 100_000],
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

function isRootMetadataAsset(path) {
  // Next emits the app manifest link as /manifest.webmanifest even when the
  // project has a basePath. It is copied at the export root and is checked by
  // presence here; analytics links still have to carry the configured prefix.
  return path === "/manifest.webmanifest" && existsSync(join(OUT, "manifest.webmanifest"));
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
      if (isRootMetadataAsset(target.path)) continue;
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
  else console.log(`Size OK ${route} ${kb} KB gzip`);
}

const failures = [];
const checked = new Set();
const sitemapFile = join(OUT, "sitemap.xml");
const sitemap = existsSync(sitemapFile) ? readFileSync(sitemapFile, "utf8") : "";
for (const route of REQUIRED_ROUTES) {
  if (!sitemap.includes(`${BASE_PATH}${route}</loc>`)) failures.push(`sitemap is missing ${route}`);
}
for (const route of REQUIRED_ROUTES) {
  const file = routeFile(route);
  if (!file) {
    failures.push(`required route missing ${route}`);
    continue;
  }
  checked.add(file);
  verifyReferences(file, readFileSync(file, "utf8"), failures);
  console.log(`Route OK ${route}`);
}
for (const [route, maxBytes] of BUDGETS) verifyBudget(route, maxBytes, failures);

if (failures.length) {
  console.error(`Analytics export verification failed (${failures.length} issue${failures.length === 1 ? "" : "s"}):`);
  for (const failure of failures) console.error(`- ${safePath(failure)}`);
  process.exitCode = 1;
} else {
  console.log(`Analytics export verification passed (${checked.size} routes, basePath ${BASE_PATH || "/"}).`);
}
