// deskExtras.server.ts -- build-time reads of the committed desk receipts that are not
// in desk/latest.json: host uptime (the newest DESK_UPTIME JSON sidecar), the newest
// issue ledger, the check_all report, and the qualification census causes. Paths are
// repo-relative (process.cwd() is webapp/). A missing file returns null and the page
// prints the reason sentence; a present but malformed receipt THROWS, so the build
// fails instead of printing a wrong number. Nothing here reads the viewer's clock.
// PAPER ONLY: operations accounting, no scored comparison, no money figure.

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { GITHUB } from "@/components/shell/nav";
import { FIGURES, FIGURES_SOURCE } from "@/lib/figures";

const REPO = join(process.cwd(), "..");
const read = (rel: string) => readFileSync(join(REPO, rel), "utf-8");
const msg = (e: unknown) => (e instanceof Error ? e.message : String(e));
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Public GitHub link for a repo-relative receipt path. */
export const ghBlob = (rel: string) => `${GITHUB}/blob/master/${rel}`;

export const EVIDENCE_DIR = "docs/evidence";
export const ISSUES_DIR = "docs/evidence/forward/issues";
export const CHECK_ALL_SRC = "scripts/platformkit/analytics_showcase/out/check_all_report.json";
export const CENSUS_SRC = "docs/evidence/harness/QUALIFICATION_CENSUS_2026-10-20.md";
export const PACKET_SRC = "docs/JOB_EVIDENCE_PACKET.md";

// The uptime sidecar carries no as_of key: its date is in its file name, so the newest
// DESK_UPTIME_<date>.json is the receipt and that date is its as-of.
export const UPTIME_RE = /^DESK_UPTIME_(\d{4}-\d{2}-\d{2})\.json$/;
function newestUptime(): string | null {
  try {
    return readdirSync(join(REPO, EVIDENCE_DIR)).filter((n) => UPTIME_RE.test(n)).sort().pop() ?? null;
  } catch {
    return null;
  }
}
export const UPTIME_SRC = `${EVIDENCE_DIR}/${newestUptime() ?? "DESK_UPTIME_<date>.json"}`;
export const UPTIME_DOC = UPTIME_SRC.replace(/\.json$/, ".md");

export type UptimeDay = {
  date: string; scheduled: boolean; served: number; night: string | null; reasons: string[]; attempt_file: boolean;
};
export type Uptime = {
  window: string; asOf: string; days: number; scheduled: number; served: number; scored: number;
  complete: number; partial: number; share: number; noReceipt: number; table: UptimeDay[];
  partialReasons: Record<string, number>;
};

const UPTIME_NUMERICS = [
  "days", "scheduled", "served", "scored", "scored_complete", "scored_partial", "scored_share", "no_receipt_days",
] as const;

/** The uptime receipt at `rel` (default: the newest). Missing -> null; malformed -> throws. */
export function loadUptime(rel = UPTIME_SRC): Uptime | null {
  let raw: string;
  try {
    raw = read(rel);
  } catch {
    return null;
  }
  const asOf = UPTIME_RE.exec(rel.split("/").pop() ?? "")?.[1];
  if (!asOf) throw new Error(`${rel}: an uptime receipt is named DESK_UPTIME_<YYYY-MM-DD>.json; that date is its as-of`);
  let j: Record<string, unknown>;
  try {
    j = JSON.parse(raw) as Record<string, unknown>;
  } catch (e) {
    throw new Error(`${rel}: not valid JSON: ${msg(e)}`);
  }
  const n = {} as Record<(typeof UPTIME_NUMERICS)[number], number>;
  for (const k of UPTIME_NUMERICS) {
    const v = j[k];
    if (!finite(v)) throw new Error(`${rel}: "${k}" must be a finite number, got ${JSON.stringify(v)}`);
    n[k] = v;
  }
  const table = Array.isArray(j.table) ? (j.table as UptimeDay[]) : [];
  if (!table.length) throw new Error(`${rel}: "table" must be a non-empty array of days`);
  for (const d of table) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(d.date)) || !finite(d.served) || !Array.isArray(d.reasons)
      || (d.night !== null && typeof d.night !== "string")) {
      throw new Error(`${rel}: malformed table row ${JSON.stringify(d)}`);
    }
  }
  return {
    window: `${table[0].date} to ${table[table.length - 1].date}`, asOf,
    days: n.days, scheduled: n.scheduled, served: n.served, scored: n.scored,
    complete: n.scored_complete, partial: n.scored_partial, share: n.scored_share,
    noReceipt: n.no_receipt_days, table, partialReasons: (j.partial_reasons as Record<string, number>) ?? {},
  };
}

export type Issues = { file: string; date: string; open: number; total: number };

/** Newest docs/evidence/forward/issues/<D>.md and its "counts: open=N total=M" line. */
export function loadIssues(): Issues | null {
  try {
    const names = readdirSync(join(REPO, ISSUES_DIR)).filter((n) => /^\d{4}-\d{2}-\d{2}\.md$/.test(n)).sort();
    const name = names[names.length - 1];
    if (!name) return null;
    const m = /counts:\s*open=(\d+)\s+total=(\d+)/.exec(read(`${ISSUES_DIR}/${name}`));
    if (!m) return null;
    return { file: `${ISSUES_DIR}/${name}`, date: name.slice(0, 10), open: Number(m[1]), total: Number(m[2]) };
  } catch {
    return null;
  }
}

/** PASS / NO_CHECK / other (FAIL, ERROR, unknown) counts; `other` is total - pass - noCheck. */
export type Checks = { pass: number; noCheck: number; other: number; total: number; asOf: string };

/**
 * check_all.py's own report (the home page reads the same). Missing -> null (the page
 * says the report is not on this clone). A row that is neither PASS nor NO_CHECK, or a
 * report with no as_of, THROWS: the count would otherwise silently omit the failures.
 */
export function loadChecks(rel = CHECK_ALL_SRC): Checks | null {
  let raw: string;
  try {
    raw = read(rel);
  } catch {
    return null;
  }
  const rows = JSON.parse(raw) as { module?: string; status?: string; as_of?: string }[];
  if (!Array.isArray(rows) || !rows.length) throw new Error(`${rel}: expected a non-empty array of check rows`);
  const asOf = rows.map((x) => x.as_of ?? "").sort().pop()?.slice(0, 10) ?? "";
  const pass = rows.filter((x) => x.status === "PASS").length;
  const noCheck = rows.filter((x) => x.status === "NO_CHECK").length;
  const other = rows.length - pass - noCheck;
  if (other > 0) {
    const named = rows.filter((x) => x.status !== "PASS" && x.status !== "NO_CHECK")
      .map((x) => `${x.module ?? "?"}=${x.status ?? "missing"}`);
    throw new Error(`${rel}: ${other} of ${rows.length} module self-checks are FAIL/other: ${named.join(", ")}`);
  }
  if (!asOf) throw new Error(`${rel}: no row carries an as_of, so the report cannot be dated`);
  return { pass, noCheck, other, total: rows.length, asOf };
}

// Qualification census 2026-10-06..10-16, transcribed from the census memo's one-paragraph
// answer (the memo is prose, so the per-cause counts are fixed here with their source).
// The served total and the PASS count come from the canonical forward_window_counts
// figure, and the causes must sum to that total: a drift between the two fails the build.
const FORWARD = FIGURES.forward_window_counts;
const CENSUS_CAUSES = [
  { cause: "never judged", n: 79,
    why: "three qualification steps were killed before writing a receipt (45 games), the 10-10 receipt was refused undeclared_sport (26) and night 10-15 never ran (8)" },
  { cause: "no capture", n: 11, why: "the laptop was asleep, so the game has no tape to grade" },
  { cause: "COVERAGE_LOW", n: 23,
    why: "every game with live capture covered under the 90 pct floor; the best reached 80.5 pct" },
] as const;
const causeSum = CENSUS_CAUSES.reduce<number>((a, c) => a + c.n, 0);
if (causeSum !== FORWARD.games_served) {
  throw new Error(`CENSUS causes sum to ${causeSum} games but ${FIGURES_SOURCE} forward_window_counts.games_served is ${FORWARD.games_served}`);
}
const judged = /^(\d+) of (\d+)$/.exec(FORWARD.qualified_of_judged);
if (!judged) throw new Error(`${FIGURES_SOURCE} forward_window_counts.qualified_of_judged is not "<pass> of <judged>"`);

export const CENSUS = {
  asOf: /_(\d{4}-\d{2}-\d{2})\.md$/.exec(CENSUS_SRC)?.[1] ?? "not stated",
  window: `2026-10-06 to ${FORWARD.window_end}`,
  served: FORWARD.games_served,
  pass: Number(judged[1]),
  causes: CENSUS_CAUSES,
} as const;

/** Minutes between two ISO stamps from the export (no wall-clock read). */
export function minutesBetween(earlier: string | null | undefined, later: string | null | undefined): number | null {
  if (!earlier || !later) return null;
  const a = Date.parse(earlier), b = Date.parse(later);
  return Number.isFinite(a) && Number.isFinite(b) ? Math.round((b - a) / 60000) : null;
}
