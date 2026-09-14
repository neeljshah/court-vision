import assert from "node:assert/strict";
import { test } from "node:test";
import { copyFileSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { webpInfo, verifyExport } from "./verify-analytics-export.mjs";

const out = resolve(fileURLToPath(new URL(".", import.meta.url)), "..", "out");

test("full export scan covers every analytics page and indexed destination", () => {
  const result = verifyExport(out);
  assert.equal(result.failures.length, 0, result.failures.join("\n"));
  assert.ok(result.htmlCount >= 1000);
  assert.ok(result.indexedCount >= 1000);
  assert.ok(result.referenceCount > result.htmlCount);
});

test("generated emblem has the required transparent dimensions", () => {
  const info = webpInfo(resolve(out, "brand", "courtvision-emblem.webp"));
  assert.deepEqual(info, { alpha: true, width: 1254, height: 1254 });
});

test("fixture scan catches nested missing routes, base path, and malformed links", () => {
  const fixture = mkdtempSync(resolve(tmpdir(), "cv-analytics-export-"));
  try {
    mkdirSync(resolve(fixture, "analytics"), { recursive: true });
    mkdirSync(resolve(fixture, "brand"), { recursive: true });
    copyFileSync(resolve(out, "brand", "courtvision-emblem.webp"), resolve(fixture, "brand", "courtvision-emblem.webp"));
    writeFileSync(resolve(fixture, "analytics", "index.html"), '<a href="/analytics/ok/">base</a><a href="/court-vision/analytics/nested/missing/">nested</a><a href="http://[bad">bad</a>');
    const records = Array.from({ length: 24 }, (_, index) => ({ id: `research-fixture-${index}`, href: "/analytics/nested/missing" }));
    writeFileSync(resolve(fixture, "analytics", "search-index.json"), JSON.stringify({ records }));
    const result = verifyExport(fixture, "/court-vision");
    assert.ok(result.failures.some((failure) => failure.includes("missing basePath for /analytics/ok/")));
    assert.ok(result.failures.some((failure) => failure.includes("references missing route or asset /analytics/nested/missing/")));
    assert.ok(result.failures.some((failure) => failure.includes("has an invalid internal reference")));
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});
