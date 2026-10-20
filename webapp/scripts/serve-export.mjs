// serve-export.mjs -- minimal static server for the exported site, mirroring the
// GitHub Pages project-site layout: http://127.0.0.1:<port>/<basePath>/... -> out/...
// Used by the a11y gate in CI and for local Lighthouse runs. Gzips text assets
// like Pages does so byte-level measurements are realistic.
//
//   node scripts/serve-export.mjs [outDir=out] [port=4173] [basePath=/court-vision]
import http from "node:http";
import { readFileSync, statSync, existsSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join, extname } from "node:path";

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
  ".png": "image/png", ".webp": "image/webp", ".avif": "image/avif", ".svg": "image/svg+xml", ".ico": "image/x-icon",
  ".woff2": "font/woff2", ".woff": "font/woff", ".txt": "text/plain", ".xml": "application/xml",
  ".webmanifest": "application/manifest+json", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
};
const GZ = new Set([".html", ".js", ".css", ".json", ".svg", ".txt", ".xml", ".webmanifest"]);

/** Resolves a request path to a file under outDir, or null. Exported for the test. */
export function resolveFile(outDir, basePath, pathname) {
  let p;
  try { p = decodeURIComponent(pathname); } catch { return null; }
  if (p === basePath || p === basePath + "/") p = basePath + "/index.html";
  if (!p.startsWith(basePath + "/")) return null;
  let f = join(outDir, p.slice(basePath.length));
  if (!f.startsWith(outDir)) return null;
  if (existsSync(f) && statSync(f).isDirectory()) f = join(f, "index.html");
  if (!existsSync(f) && existsSync(f + ".html")) f = f + ".html";
  return existsSync(f) && statSync(f).isFile() ? f : null;
}

export function createServer(outDir, basePath) {
  const cache = new Map();
  return http.createServer((req, res) => {
    const f = resolveFile(outDir, basePath, new URL(req.url, "http://x").pathname);
    if (!f) { res.writeHead(404, { "content-type": "text/html" }); return res.end("<h1>404</h1>"); }
    const ext = extname(f);
    const gz = GZ.has(ext) && /\bgzip\b/.test(req.headers["accept-encoding"] || "");
    const key = f + (gz ? ".gz" : "");
    let body = cache.get(key);
    if (!body) { body = readFileSync(f); if (gz) body = gzipSync(body, { level: 6 }); cache.set(key, body); }
    const headers = { "content-type": MIME[ext] || "application/octet-stream", "content-length": body.length, "cache-control": "public, max-age=600" };
    if (gz) headers["content-encoding"] = "gzip";
    res.writeHead(200, headers);
    res.end(body);
  });
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain) {
  const outDir = process.argv[2] || "out";
  const port = Number(process.argv[3] || 4173);
  const basePath = process.argv[4] || "/court-vision";
  createServer(outDir, basePath).listen(port, () => console.log(`serving ${outDir} at http://127.0.0.1:${port}${basePath}/`));
}
