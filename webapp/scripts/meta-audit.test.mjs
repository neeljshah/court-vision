// node --test scripts/meta-audit.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { auditExport, auditPage, familyOf, parseHead, renderMarkdown, summarize } from "./meta-audit.mjs";

const ORIGIN = "https://neeljshah.github.io/court-vision";
const page = (route, extra = "") => `<html><head><title>T | CourtVision</title><meta name="description" content="Desc ${route}"/>
<link rel="canonical" href="${ORIGIN}${route}"/><meta property="og:title" content="T | CourtVision"/><meta property="og:description" content="Desc ${route}"/>
<meta property="og:url" content="${ORIGIN}${route}"/><meta name="twitter:card" content="summary_large_image"/>${extra}</head><body></body></html>`;

test("familyOf maps routes to the audited families", () => {
  assert.equal(familyOf("/"), "home");
  assert.equal(familyOf("/analytics/players/nba_players/x/"), "players");
  assert.equal(familyOf("/analytics/m/x/"), "m");
  assert.equal(familyOf("/analytics/papers/x/"), "papers");
  assert.equal(familyOf("/analytics/papers/"), "analytics");
  assert.equal(familyOf("/evidence/x/"), "evidence");
  assert.equal(familyOf("/paper/x/"), "paper");
  assert.equal(familyOf("/games/mlb/1/"), "games");
  assert.equal(familyOf("/about/"), "site");
  assert.equal(familyOf("/today/", { refresh: true }), "stub");
});

test("a complete head passes; the gaps are named", () => {
  assert.deepEqual(auditPage("/about/", parseHead(page("/about/"))), []);
  const bare = parseHead('<html><head><title>CourtVision</title><meta name="description" content="' + "x".repeat(160) + '"/></head></html>');
  assert.deepEqual(auditPage("/x/", bare), ["title", "description-long", "canonical", "og:title", "og:description", "og:url", "twitter:card"]);
  const generic = parseHead(page("/about/").replace('content="T | CourtVision"/><meta property="og:description" content="Desc /about/"', 'content="CourtVision"/><meta property="og:description" content="generic"'));
  assert.deepEqual(auditPage("/about/", generic), ["og:title", "og:description"]);
  const retracted = parseHead(page("/about/").replace("Desc /about/", "gap +18.38% here"));
  assert.ok(auditPage("/about/", retracted).includes("retracted-token"));
});

test("a stub needs noindex and may point its canonical at the destination; fill hrefs compare decoded", () => {
  const stub = parseHead(page("/today/").replace(`${ORIGIN}/today/"/><meta property="og:title"`, `${ORIGIN}/desk/"/><meta property="og:title"`) + '<meta http-equiv="refresh" content="0; url=/desk/"/>');
  assert.deepEqual(auditPage("/today/", stub), ["noindex"]);
  const fill = parseHead(page("/paper/a%257Cb/"));
  assert.deepEqual(auditPage("/paper/a%7Cb/", fill), []);
  const notFound = parseHead('<html><head><title>Not found | CourtVision</title><meta name="description" content="d"/><meta name="robots" content="noindex, follow"/><meta property="og:title" content="Not found | CourtVision"/><meta property="og:description" content="d"/><meta name="twitter:card" content="summary_large_image"/></head></html>');
  assert.deepEqual(auditPage("/404/", notFound), []);
});

test("auditExport walks the export and summarize counts duplicates per family", () => {
  const root = mkdtempSync(join(tmpdir(), "meta-audit-"));
  for (const r of ["/", "/about/", "/analytics/m/a/", "/analytics/m/b/"]) {
    mkdirSync(join(root, r), { recursive: true });
    writeFileSync(join(root, r, "index.html"), page(r === "/analytics/m/b/" ? "/analytics/m/a/" : r, r === "/" ? '<script type="application/ld+json">{}</script>' : ""));
  }
  const pages = auditExport(root);
  const s = summarize(pages);
  assert.equal(s.total.pages, 4);
  assert.equal(s.rows.find((x) => x.family === "m").duplicateDescription, 2);
  assert.equal(s.rows.find((x) => x.family === "home").jsonLd, 1);
  const md = renderMarkdown(s, pages, { verbose: true });
  assert.match(md, /\| m \| 2 \| 0 \| 2 \| 0 \|/); // both share one description; b's canonical is wrong, not missing
  assert.match(md, /\| m \| 0 \| 0 \| 1 \| 0 \|/);
  assert.match(md, /analytics\/m\/b\/: canonical-wrong, description-duplicate/);
});
