// node --test scripts/a11y-gate.test.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { triage, formatViolation, countByImpact } from "./a11y-gate.mjs";
import { resolvePage } from "./perf-pages.mjs";
import { resolveFile } from "./serve-export.mjs";

const node = (target) => ({ target: [target], html: "<x>" });

test("triage blocks serious and critical, passes moderate and minor through as advisory", () => {
  const { blocking, advisory } = triage([
    { id: "color-contrast", impact: "serious", help: "contrast", nodes: [node("p"), node("span")] },
    { id: "region", impact: "moderate", help: "landmarks", nodes: [node("div")] },
    { id: "aria-required-attr", impact: "critical", help: "aria", nodes: [node("button")] },
    { id: "empty-table-header", impact: "minor", help: "th", nodes: [] },
  ]);
  assert.deepEqual(blocking.map((v) => v.id), ["color-contrast", "aria-required-attr"]);
  assert.deepEqual(advisory.map((v) => v.id), ["region", "empty-table-header"]);
  assert.equal(blocking[0].nodes, 2);
  assert.deepEqual(blocking[0].targets, ["p", "span"]);
});

test("formatViolation names page, theme, rule, impact, count and first targets", () => {
  const line = formatViolation("/desk/", "light", { id: "color-contrast", impact: "serious", nodes: 3, help: "Elements must meet minimum color contrast", targets: [".a", ".b"] });
  assert.equal(line, "/desk/ [light] color-contrast (serious) x3: Elements must meet minimum color contrast -- .a | .b");
});

test("resolveFile maps the project-site basePath onto the export and refuses escapes", () => {
  const root = mkdtempSync(join(tmpdir(), "serve-export-"));
  mkdirSync(join(root, "desk"), { recursive: true });
  writeFileSync(join(root, "index.html"), "home");
  writeFileSync(join(root, "desk", "index.html"), "desk");
  writeFileSync(join(root, "404.html"), "nope");
  assert.equal(resolveFile(root, "/cv", "/cv/"), join(root, "index.html"));
  assert.equal(resolveFile(root, "/cv", "/cv"), join(root, "index.html"));
  assert.equal(resolveFile(root, "/cv", "/cv/desk/"), join(root, "desk", "index.html"));
  assert.equal(resolveFile(root, "/cv", "/cv/desk"), join(root, "desk", "index.html"));
  assert.equal(resolveFile(root, "/cv", "/cv/404"), join(root, "404.html"));
  assert.equal(resolveFile(root, "/cv", "/desk/"), null);
  assert.equal(resolveFile(root, "/cv", "/cv/../../etc/passwd"), null);
  assert.equal(resolveFile(root, "/cv", "/cv/missing/"), null);
});

test("resolvePage expands manifest bet ids with the site's double encoding and passes plain paths through", () => {
  // manifest.bet_ids are stored already percent-encoded (the export directory names);
  // the href encodes them once more, as lib/paperLinks.ts does, so the host's single
  // decode lands on the directory.
  const manifest = { bet_ids: ["mlb%7Cmlb%7CTB%20Rays%7C2026-07-03T21%3A00%3A45.173950%2B00%3A00%7Cprop"] };
  assert.equal(resolvePage("/desk/", manifest), "/desk/");
  assert.equal(resolvePage("manifest:bet_ids:0", manifest), "/paper/mlb%257Cmlb%257CTB%2520Rays%257C2026-07-03T21%253A00%253A45%2E173950%252B00%253A00%257Cprop/");
  assert.equal(resolvePage("manifest:bet_ids:5", manifest), null);
  assert.equal(resolvePage("manifest:bet_ids:0", null), null);
});

test("countByImpact tallies each impact level", () => {
  assert.deepEqual(countByImpact([{ impact: "serious" }, { impact: "serious" }, { impact: "minor" }, { impact: null }]), { critical: 0, serious: 2, moderate: 0, minor: 1 });
});
