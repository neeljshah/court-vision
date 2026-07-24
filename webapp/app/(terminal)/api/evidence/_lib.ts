// _lib.ts -- shared reducer for GET /api/evidence (the m44 append-only
// evidence series, data/frontend/exec_evidence_series.jsonl, one vintage/hour
// -- see scripts/platformkit/evidence/exec_evidence_series.py). Lives outside
// route.ts because Next route modules may only export route handlers/config.
// READ-ONLY: never writes data/.

import path from "node:path";

export const EVIDENCE_SERIES_PATH = path.join(
  process.cwd(),
  process.cwd().endsWith("webapp") ? ".." : ".",
  "data",
  "frontend",
  "exec_evidence_series.jsonl",
);

type ClvBlock = { median_clv_pct: number | null; n: number };
type SnapshotRow = { ts?: string; clv_by_market?: Record<string, ClvBlock> };

export type EvidenceDayPoint = { date: string; median_clv_pct: number | null; n: number };
export type EvidenceResponse = {
  status: "ok" | "unavailable";
  series_by_market: Record<string, EvidenceDayPoint[]>;
  latest: Record<string, ClvBlock>;
  n_vintages: number;
  as_of: string | null;
  reason?: string;
};

// Pure reducer -- same rule as the Python summarize_series: hourly vintages
// collapse to one daily point per market, the LAST vintage of the day wins
// (rows are append-ordered). Malformed/blank lines are skipped, never thrown.
export function reduceSeries(lines: string[]): Omit<EvidenceResponse, "status" | "as_of"> {
  const byMarketDay = new Map<string, Map<string, ClvBlock>>();
  const latest: Record<string, ClvBlock> = {};
  let nVintages = 0;
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    let row: SnapshotRow;
    try {
      row = JSON.parse(trimmed) as SnapshotRow;
    } catch {
      continue;
    }
    nVintages += 1;
    const day = (row.ts ?? "").slice(0, 10);
    for (const [market, block] of Object.entries(row.clv_by_market ?? {})) {
      if (!byMarketDay.has(market)) byMarketDay.set(market, new Map());
      if (day) byMarketDay.get(market)!.set(day, block); // last vintage of the day wins
      latest[market] = block; // last row overall wins -- rows are append-ordered
    }
  }
  const series_by_market: Record<string, EvidenceDayPoint[]> = {};
  for (const [market, dayMap] of byMarketDay) {
    series_by_market[market] = Array.from(dayMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, block]) => ({ date, median_clv_pct: block.median_clv_pct, n: block.n }));
  }
  return { series_by_market, latest, n_vintages: nVintages };
}
