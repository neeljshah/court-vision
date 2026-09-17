import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { verifyPublicJson } from "./verify-public-json.mjs";

test("every committed analytics JSON parses and the unavailable ledger p stays null", () => {
  const result = verifyPublicJson();
  assert.ok(result.fileCount >= 372);
  assert.deepEqual(result.failures, []);
  const ledger = JSON.parse(readFileSync(new URL("../public/data/showcase/mechanism_ledger_export.json", import.meta.url), "utf8"));
  const rows = Object.values(ledger.by_sport).flatMap(sport => sport.mechanisms);
  const matches = rows.filter(item => item.mechanism === "break_point_conversion_by_set_number"
    && item.corpus === "slam_points_2011_2015" && item.verdict === "NOT_TESTABLE");
  assert.equal(matches.length, 1);
  const [row] = matches;
  assert.equal(row.p, null);
  assert.equal(row.verdict, "NOT_TESTABLE");
  assert.equal(row.effect, -0.017);
});

test("nested malformed or non-finite JSON blocks publication; null and finite zero pass", () => {
  const fixture = mkdtempSync(join(tmpdir(), "cv-json-"));
  try {
    mkdirSync(join(fixture, "nested"));
    writeFileSync(join(fixture, "valid.json"), '{"missing":null,"zero":0,"finite":0.25}');
    const bad = ['{"p":NaN}', '{"p":Infinity}', '{"p":-Infinity}', '{"p":1e999}', '{"p":'];
    bad.forEach((value, i) => writeFileSync(join(fixture, "nested", `bad-${i}.json`), value));
    writeFileSync(join(fixture, "ignored.txt"), "Not a JSON artifact.");
    const result = verifyPublicJson(fixture);
    assert.equal(result.fileCount, 6);
    assert.equal(result.failures.length, 5);
    bad.forEach((_, i) => assert.ok(result.failures.some(message => message.startsWith(`nested/bad-${i}.json:`))));
  } finally {
    assert.equal(dirname(resolve(fixture)), resolve(tmpdir()));
    rmSync(fixture, { recursive: true, force: true });
  }
});

test("an empty or missing scan target cannot pass as verified", () => {
  const fixture = mkdtempSync(join(tmpdir(), "cv-json-empty-"));
  try {
    assert.ok(verifyPublicJson(fixture).failures.includes("No public JSON files found."));
    assert.ok(verifyPublicJson(join(fixture, "absent")).failures.length > 0);
  } finally {
    assert.equal(dirname(resolve(fixture)), resolve(tmpdir()));
    rmSync(fixture, { recursive: true, force: true });
  }
});
