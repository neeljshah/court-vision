// deskExtras.server.ts -- build-time reads of the committed desk receipts that are not
// in desk/latest.json: host uptime (DESK_UPTIME JSON sidecar), the newest issue
// ledger, the check_all report, and the qualification census causes. Paths are
// repo-relative (process.cwd() is webapp/). A missing file returns null and the
// page prints the reason sentence; nothing here reads the viewer's clock.
// PAPER ONLY: operations accounting, no scored comparison, no money figure.

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { GITHUB } from "@/components/shell/nav";

const REPO = join(process.cwd(), "..");
const read = (rel: string) => readFileSync(join(REPO, rel), "utf-8");

/** Public GitHub link for a repo-relative receipt path. */
export const ghBlob = (rel: string) => `${GITHUB}/blob/master/${rel}`;

export const UPTIME_SRC = "docs/evidence/DESK_UPTIME_2026-10-20.json";
export const UPTIME_DOC = "docs/evidence/DESK_UPTIME_2026-10-20.md";
export const ISSUES_DIR = "docs/evidence/forward/issues";
export const CHECK_ALL_SRC = "scripts/platformkit/analytics_showcase/out/check_all_report.json";
export const CENSUS_SRC = "docs/evidence/harness/QUALIFICATION_CENSUS_2026-10-20.md";
export const PACKET_SRC = "docs/JOB_EVIDENCE_PACKET.md";

export type UptimeDay = {
  date: string; scheduled: boolean; served: number; night: string; reasons: string[]; attempt_file: boolean;
};
export type Uptime = {
  window: string; asOf: string; days: number; scheduled: number; served: number; scored: number;
  complete: number; partial: number; share: number; noReceipt: number; table: UptimeDay[];
  partialReasons: Record<string, number>;
};

export function loadUptime(): Uptime | null {
  try {
    const j = JSON.parse(read(UPTIME_SRC));
    const table: UptimeDay[] = j.table ?? [];
    if (!table.length) return null;
    return {
      window: `${table[0].date} to ${table[table.length - 1].date}`,
      asOf: "2026-10-20", // ponytail: the report's date is in its file name; no as_of key in the sidecar
      days: j.days, scheduled: j.scheduled, served: j.served, scored: j.scored,
      complete: j.scored_complete, partial: j.scored_partial, share: j.scored_share,
      noReceipt: j.no_receipt_days, table, partialReasons: j.partial_reasons ?? {},
    };
  } catch {
    return null;
  }
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

export type Checks = { pass: number; noCheck: number; total: number; asOf: string };

/** check_all.py's own report: PASS / NO_CHECK counts and its newest as_of (same read as the home page). */
export function loadChecks(): Checks | null {
  try {
    const rows = JSON.parse(read(CHECK_ALL_SRC)) as { status: string; as_of?: string }[];
    const asOf = rows.map((x) => x.as_of ?? "").sort().pop()?.slice(0, 10) ?? "";
    return { pass: rows.filter((x) => x.status === "PASS").length,
      noCheck: rows.filter((x) => x.status === "NO_CHECK").length, total: rows.length, asOf };
  } catch {
    return null;
  }
}

/**
 * Qualification census 2026-10-06..10-16 (as of 2026-10-20), transcribed from the
 * census memo's one-paragraph answer. The memo is prose, so the counts are fixed
 * here with their source rather than parsed.
 */
export const CENSUS = {
  asOf: "2026-10-20",
  window: "2026-10-06 to 2026-10-16",
  served: 113,
  pass: 0,
  causes: [
    { cause: "never judged", n: 79,
      why: "three qualification steps were killed before writing a receipt (45 games), the 10-10 receipt was refused undeclared_sport (26) and night 10-15 never ran (8)" },
    { cause: "no capture", n: 11, why: "the laptop was asleep, so the game has no tape to grade" },
    { cause: "COVERAGE_LOW", n: 23,
      why: "every game with live capture covered under the 90 pct floor; the best reached 80.5 pct" },
  ],
} as const;

/** Minutes between two ISO stamps from the export (no wall-clock read). */
export function minutesBetween(earlier: string | null | undefined, later: string | null | undefined): number | null {
  if (!earlier || !later) return null;
  const a = Date.parse(earlier), b = Date.parse(later);
  return Number.isFinite(a) && Number.isFinite(b) ? Math.round((b - a) / 60000) : null;
}
