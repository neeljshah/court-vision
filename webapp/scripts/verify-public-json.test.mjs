import assert from "node:assert/strict";
import { test } from "node:test";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
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

test("the site gate passes on this clone's committed artifacts, live and snapshot", async () => {
  const { verifySite } = await import("./verify-public-json.mjs");
  const { ARTIFACT_RULES } = await import("./verify-public-rules.mjs");
  for (const snapshot of [false, true]) {
    const result = verifySite({ snapshot });
    assert.deepEqual(result.failures, [], `snapshot=${snapshot}`);
    assert.ok(result.fileCount >= 372 + 100);
    assert.equal(result.checked, ARTIFACT_RULES.length);
  }
});

test("the artifact rules name a wrong key type, a missing export file, a bad status and an inverted interval", async () => {
  const { verifySite } = await import("./verify-public-json.mjs");
  const webapp = mkdtempSync(join(tmpdir(), "cv-site-"));
  const repo = mkdtempSync(join(tmpdir(), "cv-repo-"));
  try {
    mkdirSync(join(webapp, "public", "data", "showcase"), { recursive: true });
    mkdirSync(join(webapp, "public", "demo-data"));
    mkdirSync(join(repo, "docs", "evidence"), { recursive: true });
    writeFileSync(join(webapp, "public", "data", "ok.json"), '{"p":0.5}');
    writeFileSync(join(webapp, "public", "data", "showcase", "check_all_report.json"),
      JSON.stringify([{ module: "a.py", status: "ERROR", as_of: "2026-10-20T00:00:00Z" }]));
    writeFileSync(join(webapp, "public", "demo-data", "manifest.json"),
      JSON.stringify({ generated_at: "2026-07-16T01:45:31Z", games: [{ sport: "mlb" }], bet_ids: [] }));
    writeFileSync(join(webapp, "public", "demo-data", "api_paper_trail_limit_400.json"),
      JSON.stringify({ status: "ok", trail: [{ game_id: "G", sport: "mlb", status: "settled", graded: "yes", executed: false, ts: "t",
        stake_units: 1, clv_pct: null, clv_is_proxy: false, outcome: null }] }));
    writeFileSync(join(repo, "docs", "evidence", "CANONICAL_FIGURES.json"), JSON.stringify({
      schema: "canonical_figures/v1", as_of: "2026-10-06",
      figures: [{ key: "mlb_ml_pregame_vs_close", verdict: "TRAILS_CLOSE", as_of: "2026-09-24", source: "s", n: 10, ci95: [0.2, 0.1] }],
    }));
    const { failures } = verifySite({ webappRoot: webapp, repoRoot: repo, snapshot: true });
    const expected = [
      'public/demo-data/manifest.json: "bet_ids" must be a non-empty array, got []',
      'public/demo-data/manifest.json.games[0]: "game_id" must be a non-empty string, got "absent"',
      'public/demo-data/api_paper_trail_limit_400.json.trail[0]: "graded" must be a boolean, got "yes"',
      "public/demo-data/api_paper_clv.json: missing (the snapshot export is incomplete)",
      "public/receipts.json: missing",
      'public/data/showcase/check_all_report.json[0]: "status" must be a status among PASS/NO_CHECK/FAIL, got "ERROR"',
      '<repo>/docs/evidence/CANONICAL_FIGURES.json.figures[0]: "ci95" lo 0.2 exceeds hi 0.1',
      '<repo>/docs/evidence/CANONICAL_FIGURES.json: headline figure "soccer_ou25_pregame_vs_close" is missing',
      "<repo>/docs/evidence/DESK_UPTIME_<date>.json: missing",
    ];
    for (const message of expected) assert.ok(failures.includes(message), `${message}\n--- got:\n${failures.join("\n")}`);
  } finally {
    rmSync(webapp, { recursive: true, force: true });
    rmSync(repo, { recursive: true, force: true });
  }
});

test("without an export a live build skips the demo rules, a snapshot build fails", async () => {
  const { verifySite } = await import("./verify-public-json.mjs");
  const webapp = mkdtempSync(join(tmpdir(), "cv-noexport-"));
  try {
    mkdirSync(join(webapp, "public", "data"), { recursive: true });
    writeFileSync(join(webapp, "public", "data", "ok.json"), "{}");
    const repo = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
    const live = verifySite({ webappRoot: webapp, repoRoot: repo, snapshot: false });
    assert.ok(!live.failures.some((f) => f.startsWith("public/demo-data")), live.failures.join("\n"));
    const snap = verifySite({ webappRoot: webapp, repoRoot: repo, snapshot: true });
    assert.ok(snap.failures.some((f) => f.startsWith("public/demo-data: missing")), snap.failures.join("\n"));
    assert.ok(snap.failures.includes("public/demo-data/manifest.json: missing (the snapshot export is incomplete)"));
  } finally {
    rmSync(webapp, { recursive: true, force: true });
  }
});
