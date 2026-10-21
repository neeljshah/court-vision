// third-party-requests.mjs -- the request inventory behind the footer line. Serves the
// export the way GitHub Pages does, loads each page with the runner's Chrome, exercises
// the palette and the theme toggle, and records every request whose host is not the
// site's own origin, plus any cookie set. Prints a Markdown table and a ```json blob;
// exits non-zero when a third-party host or a cookie shows up, so the footer's
// "no analytics, no cookies, no third-party requests" claim cannot drift silently.
// ASCII only.
//
//   A11Y_CHROME=/path/to/chrome node scripts/third-party-requests.mjs [outDir=out] [pagesFile=perf/keyboard-pages.json]
import { readFileSync } from "node:fs";
import { createServer } from "./serve-export.mjs";
import { resolvePage, readManifest } from "./perf-pages.mjs";
import { launchChrome } from "./browser.mjs";
import { hostKind } from "./crawl-links.mjs";

/** Group the requests of one page by host, labelled fonts / analytics / cdn / other. Exported for the test. */
export function summarize(requests, ownHost) {
  const hosts = new Map();
  for (const r of requests) {
    let host;
    try { host = new URL(r.url).host; } catch { continue; }
    if (host === ownHost) continue;
    const h = hosts.get(host) || { host, kind: hostKind(host), types: {}, count: 0 };
    h.count += 1;
    h.types[r.type] = (h.types[r.type] || 0) + 1;
    hosts.set(host, h);
  }
  return [...hosts.values()].sort((a, b) => b.count - a.count);
}

export function formatReport(rows) {
  const L = ["| page | requests | own-origin | third-party hosts | cookies |", "|---|---:|---:|---|---|"];
  for (const r of rows) L.push(`| ${r.page} | ${r.requests} | ${r.own} | ${r.hosts.map((h) => `${h.host} (${h.kind}, ${h.count})`).join(", ") || "none"} | ${r.cookies.length ? r.cookies.join(", ") : "none"} |`);
  return L.join("\n");
}

async function inventory(browser, base, ownHost, page) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const requests = [];
  ctx.on("request", (req) => requests.push({ url: req.url(), type: req.resourceType() }));
  const pg = await ctx.newPage();
  try {
    await pg.goto(base + page, { waitUntil: "networkidle" });
    await pg.waitForTimeout(300);
    // The lazy palette fetches its index; the theme toggle swaps stylesheet tokens.
    await pg.keyboard.press("Control+k");
    try { await pg.locator("[role=dialog]").first().waitFor({ state: "visible", timeout: 6000 }); } catch { /* reported by keyboard-walk */ }
    await pg.waitForTimeout(400);
    await pg.keyboard.press("Escape");
    const toggle = pg.locator('button[aria-label="Dark theme"]');
    if (await toggle.count()) { await toggle.first().click(); await pg.waitForTimeout(200); }
    await pg.waitForLoadState("networkidle");
    const cookies = (await ctx.cookies()).map((c) => `${c.name}@${c.domain}`);
    const hosts = summarize(requests, ownHost);
    return { page, requests: requests.length, own: requests.length - hosts.reduce((n, h) => n + h.count, 0), hosts, cookies };
  } finally {
    await ctx.close();
  }
}

const isMain = process.argv[1] && import.meta.url.endsWith(process.argv[1].split("/").pop());
if (isMain) {
  const outDir = process.argv[2] || "out";
  const config = JSON.parse(readFileSync(process.argv[3] || "perf/keyboard-pages.json", "utf8"));
  const manifest = readManifest();
  const pages = config.pages.map((entry) => resolvePage(entry, manifest)).filter(Boolean);
  const server = createServer(outDir, config.basePath);
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const ownHost = `127.0.0.1:${server.address().port}`;
  const base = `http://${ownHost}${config.basePath}`;
  const rows = [];
  const browser = await launchChrome("third-party-requests");
  try {
    for (const page of pages) rows.push(await inventory(browser, base, ownHost, page));
  } finally {
    await browser.close();
    server.close();
  }
  console.log(formatReport(rows));
  const offenders = rows.filter((r) => r.hosts.length || r.cookies.length);
  console.log("\n```json\n" + JSON.stringify({ ownHost, pages, rows }) + "\n```");
  if (offenders.length) {
    console.error(`\nthird-party-requests: ${offenders.length} page(s) reached a third-party host or set a cookie`);
    process.exit(1);
  }
  console.log(`\nthird-party-requests GREEN: ${pages.length} pages, ${rows.reduce((n, r) => n + r.requests, 0)} requests, all to ${ownHost}; no cookies.`);
}
