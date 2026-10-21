// crawl-links.mjs -- the pure helpers behind scripts/crawl-export.mjs: attribute
// extraction from exported HTML, link classification against the Pages basePath,
// the retired-route map read off lib/redirects.ts, page families and anchor ids.
// No I/O here except reading redirects.ts; the walker and the report live in
// crawl-export.mjs so each stays testable (node --test scripts/crawl-export.test.mjs).
import { readFileSync } from "node:fs";

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", "#39": "'", "#x27": "'", "#x2F": "/" };
export const decodeEntities = (s) => s.replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (m, e) => {
  if (ENTITIES[e] !== undefined) return ENTITIES[e];
  if (e[0] === "#") return String.fromCodePoint(parseInt(e[1] === "x" || e[1] === "X" ? e.slice(2) : e.slice(1), e[1] === "x" || e[1] === "X" ? 16 : 10));
  return m;
});

/** Every href / src (and a meta refresh url) in the markup, with the tag that carries it.
 *  Script and style bodies are blanked first so a serialized RSC payload or a CSS url()
 *  never reads as a link; the <script src> open tags themselves are kept. */
export function extractRefs(html) {
  const refs = [];
  const stripped = html
    .replace(/(<script\b[^>]*>)[\s\S]*?<\/script>/gi, "$1</script>")
    .replace(/(<style\b[^>]*>)[\s\S]*?<\/style>/gi, "$1</style>")
    .replace(/<!--[\s\S]*?-->/g, "");
  const tagRe = /<([a-zA-Z][\w-]*)\b([^>]*)>/g;
  let m;
  while ((m = tagRe.exec(stripped))) {
    const tag = m[1].toLowerCase(), attrs = m[2];
    const attrRe = /\s(href|src)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))/gi;
    let a;
    while ((a = attrRe.exec(attrs))) refs.push({ tag, attr: a[1].toLowerCase(), value: decodeEntities(a[2] ?? a[3] ?? a[4] ?? "") });
    if (tag === "meta" && /http-equiv\s*=\s*["']?refresh/i.test(attrs)) {
      const c = /content\s*=\s*(?:"([^"]*)"|'([^']*)')/i.exec(attrs);
      const url = c && /url\s*=\s*(.+)$/i.exec(decodeEntities(c[1] ?? c[2] ?? ""));
      if (url) refs.push({ tag: "meta", attr: "refresh", value: url[1].trim() });
    }
  }
  return refs;
}

/** All id= / name= values on a page (the anchor targets). */
export function extractIds(html) {
  const ids = new Set();
  const re = /<[a-zA-Z][^>]*\s(?:id|name)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
  let m;
  while ((m = re.exec(html))) ids.add(decodeEntities(m[1] ?? m[2] ?? ""));
  return ids;
}

/** The exported page path of an out/ file: "desk/index.html" -> "/desk/", "404.html" -> "/404.html". */
export function pagePath(rel) {
  const p = "/" + rel.split("\\").join("/");
  return p.endsWith("/index.html") ? p.slice(0, -"index.html".length) : p;
}

/** Report family: first path segment, plus the second one under /analytics (its many sections). */
export function familyOf(path) {
  const segs = path.replace(/\/+$/, "").split("/").filter(Boolean);
  if (!segs.length) return "home";
  if (segs[0] === "404.html") return "404";
  if (segs[0] === "analytics" && segs.length > 1) return `analytics/${segs[1]}`;
  return segs[0];
}

export const SKIP_SCHEMES = /^(mailto|tel|javascript|data|blob|sms):/i;

/**
 * Classify one reference found on `fromPath` (basePath-free page path such as "/desk/").
 * Internal links are resolved the way GitHub Pages does: one percent-decode, then a
 * directory's index.html, a file, or "<path>.html" (served, but only without the slash).
 * `files` is the set of exported relative paths ("desk/index.html"); `ids(rel)` returns
 * the id set of an exported file; `stubs` maps a retired basePath-free path to its target.
 */
export function classify(ref, fromPath, ctx) {
  const { basePath, origin, files, ids, stubs, prefixStubs } = ctx;
  const raw = ref.value.trim();
  if (!raw || SKIP_SCHEMES.test(raw)) return { kind: "skip" };
  const fromRel = fromPath.endsWith("/") ? fromPath.slice(1) + "index.html" : fromPath.slice(1);
  if (raw[0] === "#") {
    // Same-page anchor: never a navigation, so only the id is checked (on this very file).
    const id = (() => { try { return decodeURIComponent(raw.slice(1)); } catch { return raw.slice(1); } })();
    return { kind: "ok", path: fromPath, target: fromRel, noSlash: false, badAnchor: id && !ids(fromRel).has(id) ? id : undefined };
  }
  // The on-disk page path is the once-decoded URL path (a fill directory is literally
  // "mlb%7C..."), so the base URL re-encodes each segment: one decode lands on the file.
  const base = `${origin}${basePath}${fromPath.split("/").map(encodeURIComponent).join("/")}`;
  let url;
  try { url = new URL(raw, base); } catch { return { kind: "malformed" }; }
  if (!/^https?:$/.test(url.protocol)) return { kind: "skip" };
  if (url.origin !== origin) return { kind: "external", host: url.host };
  if (url.pathname !== basePath && !url.pathname.startsWith(basePath + "/")) {
    return { kind: "missing", detail: `outside basePath ${basePath} (404 on Pages)`, path: url.pathname };
  }
  let path = url.pathname.slice(basePath.length) || "/";
  try { path = decodeURIComponent(path); } catch { return { kind: "missing", detail: "malformed percent-encoding", path }; }
  const rel = path.replace(/^\/+/, "");
  let target = null, noSlash = false;
  if (path.endsWith("/")) {
    if (files.has(rel + "index.html")) target = rel + "index.html";
  } else if (files.has(rel)) {
    target = rel;
  } else if (files.has(rel + "/index.html")) {
    target = rel + "/index.html"; noSlash = true;
  } else if (files.has(rel + ".html")) {
    target = rel + ".html";
  }
  if (!target) {
    const fam = prefixStubs.find((r) => path.startsWith(r.from) && path !== r.from);
    const detail = fam ? `retired family ${fam.from} (the 404 page forwards to ${fam.to})` : "no such file in the export";
    return { kind: "missing", detail, path };
  }
  const out = { kind: "ok", path, target, noSlash };
  const stubKey = path.endsWith("/") ? path : path + "/";
  if (stubs[stubKey]) out.stub = stubs[stubKey];
  if (url.hash && url.hash.length > 1 && target.endsWith(".html")) {
    const id = decodeURIComponent(url.hash.slice(1));
    if (!ids(target).has(id)) out.badAnchor = id;
  }
  return out;
}

/** The exact and prefix retired-route maps, read off lib/redirects.ts without a TS loader. */
export function readRedirects(file = "lib/redirects.ts") {
  const src = readFileSync(file, "utf8");
  const stubs = {};
  const exact = /^\s*"(\/[^"]*)":\s*\{\s*to:\s*"(\/[^"]*)"/gm;
  let m;
  while ((m = exact.exec(src))) stubs[m[1]] = m[2];
  const prefixStubs = [];
  const block = /PREFIX_REDIRECTS[^=]*=\s*\[([\s\S]*?)\];/.exec(src);
  if (block) {
    const pre = /from:\s*"(\/[^"]*)",\s*to:\s*"(\/[^"]*)"/g;
    while ((m = pre.exec(block[1]))) prefixStubs.push({ from: m[1], to: m[2] });
  }
  return { stubs, prefixStubs };
}

const HOST_KIND = [
  [/(^|\.)fonts\.(googleapis|gstatic)\.com$/, "fonts"],
  [/(^|\.)(typekit|fontawesome|bunny)\.(net|com)$/, "fonts"],
  [/google-analytics|googletagmanager|plausible|hotjar|mixpanel|segment\.(io|com)|posthog|umami|matomo|clarity\.ms|vercel-insights|cloudflareinsights/, "analytics"],
  [/(^|\.)(jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com|esm\.sh|skypack\.dev)$/, "cdn"],
  [/^cdn\./, "cdn"],
];
/** A label for an external host: fonts / analytics / cdn / other. */
export const hostKind = (host) => (HOST_KIND.find(([re]) => re.test(host)) || [null, "other"])[1];
