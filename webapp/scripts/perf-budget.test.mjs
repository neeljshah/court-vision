// node --test scripts/perf-budget.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pageAssets, measurePage, oversizedImages, checkBudget } from "./perf-budget.mjs";

const HTML = `<html><head>
<link rel="stylesheet" href="/cv/_next/static/css/a.css" data-precedence="next"/>
<link rel="preload" as="font" href="/cv/_next/static/media/f.woff2"/>
</head><body>
<script src="/cv/_next/static/chunks/main.js" async=""></script>
<script src="/cv/_next/static/chunks/main.js" async=""></script>
<script src="/cv/_next/static/chunks/polyfills.js" noModule=""></script>
<script src="/cv/_next/static/chunks/app/m/%5Bid%5D/page.js" async=""></script>
<script>self.__next_f=[]</script>
</body></html>`;

function exportDir() {
  const root = mkdtempSync(join(tmpdir(), "perf-budget-"));
  mkdirSync(join(root, "out", "page"), { recursive: true });
  mkdirSync(join(root, "out", "_next", "static", "chunks"), { recursive: true });
  mkdirSync(join(root, "out", "_next", "static", "css"), { recursive: true });
  mkdirSync(join(root, "public", "img"), { recursive: true });
  writeFileSync(join(root, "out", "page", "index.html"), HTML);
  writeFileSync(join(root, "out", "_next", "static", "chunks", "main.js"), "x".repeat(5000));
  mkdirSync(join(root, "out", "_next", "static", "chunks", "app", "m", "[id]"), { recursive: true });
  writeFileSync(join(root, "out", "_next", "static", "chunks", "app", "m", "[id]", "page.js"), "z".repeat(300));
  writeFileSync(join(root, "out", "_next", "static", "chunks", "polyfills.js"), "y".repeat(90000));
  writeFileSync(join(root, "out", "_next", "static", "css", "a.css"), "body{color:red}".repeat(100));
  writeFileSync(join(root, "public", "img", "big.png"), Buffer.alloc(2000));
  writeFileSync(join(root, "public", "img", "small.png"), Buffer.alloc(100));
  return root;
}

test("pageAssets dedupes scripts, drops the noModule polyfill and inline scripts, keeps stylesheets only", () => {
  const { scripts, styles } = pageAssets(HTML);
  assert.deepEqual(scripts, ["/cv/_next/static/chunks/main.js", "/cv/_next/static/chunks/app/m/%5Bid%5D/page.js"]);
  assert.deepEqual(styles, ["/cv/_next/static/css/a.css"]);
});

test("measurePage resolves assets under the basePath and reports gzip bytes", () => {
  const root = exportDir();
  const m = measurePage(join(root, "out"), "/cv", "/page/");
  assert.equal(m.jsFiles, 2);
  assert.equal(m.jsRaw, 5300); // the percent-encoded "[id]" chunk resolves to the bracketed file
  assert.ok(m.jsGz > 0 && m.jsGz < 5000);
  assert.equal(m.cssFiles, 1);
  assert.deepEqual(m.missing, []);
  assert.equal(measurePage(join(root, "out"), "/cv", "/nope/").missing, true);
});

test("oversizedImages flags only files over the cap, honouring exemptions", () => {
  const root = exportDir();
  const hits = oversizedImages(join(root, "public"), { img: { maxBytes: 1000 } });
  assert.equal(hits.length, 1);
  assert.ok(hits[0].file.endsWith("big.png"));
  assert.equal(oversizedImages(join(root, "public"), { img: { maxBytes: 1000, exempt: ["big.png"] } }).length, 0);
});

test("checkBudget passes within budget and names every breach", () => {
  const root = exportDir();
  const green = checkBudget({ basePath: "/cv", pages: { "/page/": { jsGz: 10000, cssGz: 10000, htmlGz: 10000 } }, images: { img: { maxBytes: 5000 } } }, join(root, "out"), join(root, "public"));
  assert.deepEqual(green.failures, []);
  const red = checkBudget({ basePath: "/cv", pages: { "/page/": { jsGz: 10 }, "/missing/": { jsGz: 1 }, "manifest:bet_ids:0": { jsGz: 1 } }, images: { img: { maxBytes: 1000 } } }, join(root, "out"), join(root, "public"), { bet_ids: [] });
  assert.equal(red.failures.length, 4);
  assert.match(red.failures[0], /JS \d+ bytes gzip exceeds budget 10/);
  assert.match(red.failures[1], /not exported/);
  assert.match(red.failures[2], /cannot be resolved from the demo manifest/);
  assert.match(red.failures[3], /big\.png.*exceeds image cap/);
});
