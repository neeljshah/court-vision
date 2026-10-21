#!/usr/bin/env node
// verify-public-rules.mjs -- the per-artifact key/type table behind scripts/verify-public-json.mjs.
// Each rule names one committed artifact, says whether it belongs to the snapshot export
// (public/demo-data, required when NEXT_PUBLIC_DATA_MODE=snapshot) and returns the failures
// its shape check finds. The shapes mirror the readers (lib/types.ts, paperPayload.ts
// predicates, components/desk/deskExtras.server.ts, lib/canonicalFigures.server.ts): a key
// a page renders must be present with the type the page assumes, or publication stops here.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** The home headline keys; lib/__tests__/verifyPublicRules.test.ts keeps them equal to HEADLINE_KEYS. */
export const CANONICAL_HEADLINE_KEYS = ["mlb_ml_pregame_vs_close", "soccer_ou25_pregame_vs_close", "nba_ml_pregame_vs_close_shin"];
/** The statuses check_all.py writes; any other status is a malformed report row. */
export const CHECK_STATUSES = ["PASS", "NO_CHECK", "FAIL"];
/** The uptime sidecar numerics the desk pages render (deskExtras.server UPTIME_NUMERICS). */
export const UPTIME_NUMERICS = ["days", "scheduled", "served", "scored", "scored_complete", "scored_partial", "scored_share", "no_receipt_days"];
export const UPTIME_RE = /^DESK_UPTIME_(\d{4}-\d{2}-\d{2})\.json$/;
const MAX_PER_ARTIFACT = 20;

const isBag = (v) => v !== null && typeof v === "object" && !Array.isArray(v);
const fin = (v) => typeof v === "number" && Number.isFinite(v);
// [what the key must be, predicate]
const T = {
  str: ["non-empty string", (v) => typeof v === "string" && v.length > 0],
  num: ["finite number", fin],
  bool: ["boolean", (v) => typeof v === "boolean"],
  isFalse: ["false", (v) => v === false],
  arr: ["array", Array.isArray],
  rows: ["non-empty array", (v) => Array.isArray(v) && v.length > 0],
  numOrNull: ["finite number or null", (v) => v === null || fin(v)],
  strOrNull: ["string or null", (v) => v === null || typeof v === "string"],
  numOrStr: ["finite number or string", (v) => fin(v) || typeof v === "string"],
  checkStatus: [`status among ${CHECK_STATUSES.join("/")}`, (v) => CHECK_STATUSES.includes(v)],
};

const show = (v) => JSON.stringify(v === undefined ? "absent" : v).slice(0, 80);

function shape(value, spec, where) {
  if (!isBag(value)) return [`${where}: expected an object, got ${show(value)}`];
  const out = [];
  for (const [key, [what, ok]] of Object.entries(spec)) {
    if (!ok(value[key])) out.push(`${where}: "${key}" must be a ${what}, got ${show(value[key])}`);
  }
  return out;
}
const rows = (list, spec, where) => (Array.isArray(list) ? list : []).flatMap((row, i) => shape(row, spec, `${where}[${i}]`));

const PAPER_ROW = {
  game_id: T.str, sport: T.str, status: T.str, graded: T.bool, executed: T.isFalse, ts: T.str,
  stake_units: T.numOrNull, clv_pct: T.numOrNull, clv_is_proxy: T.bool, outcome: T.strOrNull,
};
const paperTrail = (v, where) => [...shape(v, { status: T.str, trail: T.rows }, where), ...rows(v?.trail, PAPER_ROW, `${where}.trail`)];
const predictions = (v, where) => shape(v, { status: T.str, total: T.num, trades: T.arr, edge_claimed: T.isFalse }, where);
// A paper feed is either the honest sentinel ({status:"unavailable", reason}) or the shape the page reads.
const feed = (okSpec) => (v, where) =>
  isBag(v) && v.status === "unavailable" ? shape(v, { reason: T.str }, where) : shape(v, okSpec, where);
const checkAll = (v, where) =>
  !Array.isArray(v) || !v.length ? [`${where}: expected a non-empty array of check rows`]
    : rows(v, { module: T.str, status: T.checkStatus, as_of: T.str }, where);
const uptime = (v, where) => [
  ...shape(v, Object.fromEntries([...UPTIME_NUMERICS.map((k) => [k, T.num]), ["table", T.rows]]), where),
  ...rows(v?.table, { date: T.str, scheduled: T.bool, served: T.num, reasons: T.arr, night: T.strOrNull }, `${where}.table`),
];
const manifest = (v, where) => [
  ...shape(v, { generated_at: T.str, games: T.rows, bet_ids: T.rows }, where),
  ...rows(v?.games, { sport: T.str, game_id: T.str }, `${where}.games`),
  ...(Array.isArray(v?.bet_ids) ? v.bet_ids : []).flatMap((b, i) => (T.str[1](b) ? [] : [`${where}.bet_ids[${i}]: must be a non-empty string, got ${show(b)}`])),
];
const receipts = (v, where) => [
  ...shape(v, { rows: T.rows }, where),
  ...rows(v?.rows, { sport_market: T.str, checkpoint: T.str, verdict: T.str, src: T.str, n: T.numOrStr }, `${where}.rows`),
];
const explainers = (v, where) => [...shape(v, { essays: T.rows }, where), ...rows(v?.essays, { slug: T.str, title: T.str }, `${where}.essays`)];

function canonical(v, where) {
  const out = shape(v, { schema: T.str, as_of: T.str, figures: T.rows }, where);
  const figs = Array.isArray(v?.figures) ? v.figures : [];
  for (const [i, f] of figs.entries()) {
    const at = `${where}.figures[${i}]`;
    out.push(...shape(f, { key: T.str, verdict: T.str, as_of: T.str, source: T.str }, at));
    if (isBag(f) && f.ci95 !== undefined) {
      const ci = f.ci95;
      if (!Array.isArray(ci) || ci.length !== 2 || !ci.every(fin)) out.push(`${at}: "ci95" must be [lo, hi] with finite bounds, got ${show(ci)}`);
      else if (ci[0] > ci[1]) out.push(`${at}: "ci95" lo ${ci[0]} exceeds hi ${ci[1]}`);
    }
  }
  for (const key of CANONICAL_HEADLINE_KEYS) {
    const f = figs.find((x) => isBag(x) && x.key === key);
    if (!f) { out.push(`${where}: headline figure "${key}" is missing`); continue; }
    if (!fin(f.n)) out.push(`${where}: headline figure "${key}" has no finite n`);
    if (f.ci95 === undefined) out.push(`${where}: headline figure "${key}" has no ci95`);
  }
  return out;
}

/** The newest docs/evidence/DESK_UPTIME_<date>.json, or null when none is committed. */
export function newestUptime(repoRoot) {
  const dir = join(repoRoot, "docs", "evidence");
  const names = existsSync(dir) ? readdirSync(dir).filter((n) => UPTIME_RE.test(n)).sort() : [];
  return names.length ? `docs/evidence/${names[names.length - 1]}` : null;
}

/**
 * file: path relative to webapp/ (or to the repo root when root is "repo"), or a function of
 * that root returning the path (null when the artifact family is absent). demo: part of the
 * snapshot export under public/demo-data, required in a snapshot build.
 */
export const ARTIFACT_RULES = [
  { file: "public/demo-data/manifest.json", demo: true, check: manifest },
  { file: "public/demo-data/api_paper_trail_limit_400.json", demo: true, check: paperTrail },
  { file: "public/demo-data/api_paper_trail_limit_2000.json", demo: true, check: paperTrail },
  { file: "public/demo-data/api_paper_predictions_limit_500.json", demo: true, check: predictions },
  { file: "public/demo-data/api_paper_clv.json", demo: true, check: feed({ n_bets: T.num }) },
  { file: "public/demo-data/api_paper_pnl_series.json", demo: true, check: feed({ points: T.arr }) },
  { file: "public/demo-data/api_paper_bankroll.json", demo: true, check: feed({ current_units: T.num }) },
  { file: "public/receipts.json", check: receipts },
  { file: "public/data/explainers/explainers.json", check: explainers },
  { file: "public/data/showcase/check_all_report.json", check: checkAll },
  { file: "scripts/platformkit/analytics_showcase/out/check_all_report.json", root: "repo", check: checkAll },
  { file: "docs/evidence/CANONICAL_FIGURES.json", root: "repo", check: canonical },
  { file: newestUptime, root: "repo", label: "docs/evidence/DESK_UPTIME_<date>.json", check: uptime },
];

/** Runs every rule. A snapshot build requires the whole export; a live build checks whatever export is present. */
export function runArtifactRules({ webappRoot, repoRoot, snapshot = false }) {
  const failures = [];
  let checked = 0;
  const demoPresent = existsSync(join(webappRoot, "public", "demo-data"));
  if (snapshot && !demoPresent) failures.push("public/demo-data: missing; a snapshot build has no data source without the export.");
  for (const rule of ARTIFACT_RULES) {
    const base = rule.root === "repo" ? repoRoot : webappRoot;
    const rel = typeof rule.file === "function" ? rule.file(base) : rule.file;
    const label = `${rule.root === "repo" ? "<repo>/" : ""}${rel ?? rule.label}`;
    const path = rel ? join(base, rel) : null;
    if (!path || !existsSync(path)) {
      if (rule.demo && !snapshot && !demoPresent) continue; // live build without an export: nothing to check
      failures.push(`${label}: missing${rule.demo ? " (the snapshot export is incomplete)" : ""}`);
      continue;
    }
    checked += 1;
    let value;
    try {
      value = JSON.parse(readFileSync(path, "utf8"));
    } catch (error) {
      failures.push(`${label}: invalid JSON (${error instanceof Error ? error.message : String(error)})`);
      continue;
    }
    const found = rule.check(value, label);
    failures.push(...found.slice(0, MAX_PER_ARTIFACT));
    if (found.length > MAX_PER_ARTIFACT) failures.push(`${label}: ... and ${found.length - MAX_PER_ARTIFACT} more`);
  }
  return { checked, failures };
}
