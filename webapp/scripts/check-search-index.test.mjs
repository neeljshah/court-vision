import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { checkIndex, exportedFile, isRedirectStub, REQUIRED_PAGES } from "./check-search-index.mjs";

function fixture() {
  const out = mkdtempSync(join(tmpdir(), "search-index-"));
  const page = (path, html = "<html><body>ok</body></html>") => { mkdirSync(join(out, path), { recursive: true }); writeFileSync(join(out, path, "index.html"), html); };
  page("");
  for (const route of REQUIRED_PAGES) page(route.slice(1));
  page("analytics/m/zeta");
  page("analytics", '<html><body><meta http-equiv="refresh" content="0; url=/"></body></html>');
  return out;
}
const record = (id, href) => ({ id, href, title: id, subtitle: "", type: "page", keywords: [] });
const required = REQUIRED_PAGES.map((href) => record(`site${href}`, href));

test("a sound index passes", () => {
  const out = fixture();
  assert.deepEqual(checkIndex(out, [...required, record("zeta", "/analytics/m/zeta/")]), []);
  assert.ok(exportedFile(out, "/analytics/m/zeta/?q=1"));
  assert.equal(exportedFile(out, "/nowhere"), null);
});

test("missing pages, stubs and duplicate ids are reported", () => {
  const out = fixture();
  const failures = checkIndex(out, [...required.slice(1), record("stub", "/analytics"), record("gone", "/analytics/m/gone"), record("gone", "/analytics/m/zeta")]);
  assert.ok(failures.some((f) => f.includes("redirect stub")), failures.join("; "));
  assert.ok(failures.some((f) => f.includes("not in the export")));
  assert.ok(failures.some((f) => f.includes("duplicate id gone")));
  assert.ok(failures.some((f) => f.includes("site page missing from the index: /")));
  assert.equal(isRedirectStub("<meta http-equiv=\"refresh\" content=\"0; url=/x\">"), true);
  assert.equal(isRedirectStub("<p>ok</p>"), false);
});
