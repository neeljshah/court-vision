// node --test scripts/crawl-export.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { classify, extractIds, extractRefs, familyOf, hostKind, pagePath, readRedirects } from "./crawl-links.mjs";
import { crawl, formatReport } from "./crawl-export.mjs";

const ORIGIN = "https://neeljshah.github.io";
const redirects = { stubs: { "/analytics/": "/", "/paper/": "/paper-trading/" }, prefixStubs: [{ from: "/paper/", to: "/paper-trading/" }] };

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "crawl-export-"));
  const w = (rel, html) => { mkdirSync(join(root, rel, ".."), { recursive: true }); writeFileSync(join(root, rel), html); };
  w("index.html", `<html><body><a href="#main-content">Skip</a><main id="main-content">
    <a href="/court-vision/desk/">desk</a> <a href="/court-vision/desk">no slash</a>
    <a href="/court-vision/analytics/">stub</a> <a href="/court-vision/missing/">gone</a>
    <a href="/court-vision/desk/#refusals">anchor ok</a> <a href="/court-vision/desk/#nope">anchor bad</a>
    <a href="/desk/">outside base</a> <a href="https://github.com/x">gh</a> <a href="mailto:a@b.c">mail</a>
    <a href="/court-vision/paper/mlb%257C1/">fill</a> <a href="/court-vision/paper/other/">retired fill</a>
    <script src="/court-vision/_next/static/a.js"></script><script>var s = '<a href="/court-vision/not-a-link/">x</a>';</script>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter" /></main></body></html>`);
  w("desk/index.html", `<html><body><h2 id="refusals">r</h2><img src="/court-vision/img/x.png" /><a href="https://neeljshah.github.io/court-vision/">abs home</a></body></html>`);
  w("analytics/index.html", `<html><body><meta http-equiv="refresh" content="0; url=/court-vision/" /><h1 id="moved-title">This page moved</h1></body></html>`);
  w("paper/index.html", `<html><body><meta http-equiv="refresh" content="0; url=/court-vision/paper-trading/" /><h1 id="moved-title">This page moved</h1></body></html>`);
  w("paper-trading/index.html", `<html><body><main id="main-content"></main></body></html>`);
  w("paper/mlb%7C1/index.html", `<html><body><a href="#main-content">skip</a><main id="main-content"></main><a href="/court-vision/paper/">back</a></body></html>`);
  w("_next/static/a.js", "");
  w("img/x.png", "");
  return root;
}

test("extractRefs reads href/src with the carrying tag, decodes entities, skips script bodies", () => {
  const refs = extractRefs(`<a href="/a?x=1&amp;y=2">a</a><script src='/s.js'></script><script>"<a href=/no>"</script><img src=/i.png><meta http-equiv="refresh" content="0; url=/go/">`);
  assert.deepEqual(refs, [
    { tag: "a", attr: "href", value: "/a?x=1&y=2" }, { tag: "script", attr: "src", value: "/s.js" },
    { tag: "img", attr: "src", value: "/i.png" }, { tag: "meta", attr: "refresh", value: "/go/" },
  ]);
  assert.deepEqual([...extractIds(`<main id="main-content"><a name="top"></a><p id='x'>`)], ["main-content", "top", "x"]);
});

test("pagePath, familyOf and hostKind", () => {
  assert.equal(pagePath("desk/index.html"), "/desk/");
  assert.equal(pagePath("index.html"), "/");
  assert.equal(pagePath("404.html"), "/404.html");
  assert.equal(familyOf("/"), "home");
  assert.equal(familyOf("/404.html"), "404");
  assert.equal(familyOf("/analytics/players/nba/x/"), "analytics/players");
  assert.equal(familyOf("/paper/mlb%7C1/"), "paper");
  assert.equal(hostKind("fonts.gstatic.com"), "fonts");
  assert.equal(hostKind("www.googletagmanager.com"), "analytics");
  assert.equal(hostKind("cdn.jsdelivr.net"), "cdn");
  assert.equal(hostKind("github.com"), "other");
});

test("classify resolves like GitHub Pages: basePath, one decode, directory index, slash, stub, anchor", () => {
  const root = fixture();
  const files = new Set(["index.html", "desk/index.html", "analytics/index.html", "paper/mlb%7C1/index.html", "_next/static/a.js", "img/x.png"]);
  const ids = (rel) => (rel === "desk/index.html" ? new Set(["refusals"]) : new Set(["main-content"]));
  const ctx = { basePath: "/court-vision", origin: ORIGIN, files, ids, ...redirects };
  const c = (href, from = "/") => classify({ tag: "a", attr: "href", value: href }, from, ctx);
  assert.equal(c("/court-vision/desk/").kind, "ok");
  assert.equal(c("/court-vision/desk").noSlash, true);
  assert.equal(c("/court-vision/analytics/").stub, "/");
  assert.equal(c("/court-vision/missing/").kind, "missing");
  assert.match(c("/desk/").detail, /outside basePath/);
  assert.equal(c("/court-vision/desk/#refusals").badAnchor, undefined);
  assert.equal(c("/court-vision/desk/#nope").badAnchor, "nope");
  assert.equal(c("#main-content").kind, "ok");
  assert.equal(c("#main-content", "/paper/mlb%7C1/").badAnchor, undefined);
  assert.equal(c("#zzz").badAnchor, "zzz");
  assert.equal(c("/court-vision/paper/mlb%257C1/").target, "paper/mlb%7C1/index.html");
  assert.match(c("/court-vision/paper/other/").detail, /retired family \/paper\//);
  assert.equal(c("/court-vision/_next/static/a.js").kind, "ok");
  assert.equal(c("https://neeljshah.github.io/court-vision/").kind, "ok");
  assert.deepEqual(c("https://github.com/x"), { kind: "external", host: "github.com" });
  assert.equal(c("mailto:a@b.c").kind, "skip");
  assert.equal(c("javascript:void(0)").kind, "skip");
  void root;
});

test("crawl tallies by family, ranks offenders by severity and counts external hosts by tag", () => {
  const res = crawl(fixture(), "/court-vision", redirects, { top: 30 });
  assert.deepEqual(res.totals, { pages: 6, links: 19, missing: 3, stub: 2, noSlash: 1, badAnchor: 1 });
  const home = res.rows.find((r) => r.family === "home");
  assert.deepEqual([home.missing, home.stub, home.noSlash, home.badAnchor], [3, 1, 1, 1]);
  assert.deepEqual(home.hosts, ["fonts.googleapis.com", "github.com"]);
  assert.equal(res.offenders[0].problem, "missing");
  assert.deepEqual(res.offenders.map((o) => o.problem), ["missing", "missing", "missing", "stub", "stub", "noSlash", "badAnchor"]);
  assert.equal(res.hrefs.find((h) => h.href === "/court-vision/paper/").detail, "stub /paper/ -> /paper-trading/");
  assert.deepEqual(res.external.map((h) => [h.host, h.kind, h.tags]), [["github.com", "other", { a: 1 }], ["fonts.googleapis.com", "fonts", { link: 1 }]]);
  const report = formatReport(res);
  assert.match(report, /\| \*\*total\*\* \| 6 \| 19 \| 3 \| 2 \| 1 \| 1 \| 2 \|/);
  assert.match(report, /\| \/ \| \/desk\/ \| missing \| outside basePath/);
});

test("readRedirects parses the exact and prefix maps out of lib/redirects.ts", () => {
  const { stubs, prefixStubs } = readRedirects();
  assert.equal(stubs["/analytics/"], "/");
  assert.equal(stubs["/evidence/retraction-story/"], "/evidence/retractions/");
  assert.ok(prefixStubs.some((r) => r.from === "/paper/" && r.to === "/paper-trading/"));
});
