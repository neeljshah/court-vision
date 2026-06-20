// venueAggregate.ts -- pure aggregation helper for per-venue PM paper-trade summary.
// Takes PaperTrailRow[] and groups by venue, returning one VenueStats object per venue.
// UNITS / probability only -- NO dollar amounts derived or stored here.
// CLV: only settled rows with a real clv_pct (non-null, clv_status != 'no_close',
// clv_unavailable=false) contribute. A venue with zero qualifying rows yields
// clv_mean=null (rendered as INSUFFICIENT_DATA, never 0-filled).

import type { PaperTrailRow } from "@/lib/p5api";
import { deriveResult } from "./PmTradeRow";

export type DerivedResult = "win" | "loss" | "void" | "pending";

export type VenueStats = {
  venue: string;
  total: number;
  open: number;
  settled: number;
  win: number;
  loss: number;
  push: number; // "void" result
  pending: number;
  stake_units_total: number | null; // null if all stakes are null
  model_prob_mean: number | null;   // mean model_prob across all rows (null if none)
  clv_mean: number | null;          // null = INSUFFICIENT_DATA (zero qualifying rows)
  clv_sample_n: number;             // count of settled rows that contributed to clv_mean
};

/** Derive canonical venue label from taken_book string. Mirrors PmTrailTable logic. */
export function venueOf(r: PaperTrailRow): string {
  const b = (r.taken_book || "").toLowerCase();
  if (b.includes("kalshi")) return "kalshi";
  if (b.includes("polymarket")) return "polymarket";
  const idx = r.taken_book?.indexOf(":") ?? -1;
  if (idx > 0) return r.taken_book!.slice(idx + 1);
  return r.taken_book || "unknown";
}

/** Return true if this row provides a real, settled CLV value (not proxy-excluded). */
function hasRealClv(r: PaperTrailRow): boolean {
  return (
    r.graded &&
    r.clv_pct != null &&
    !r.clv_unavailable &&
    r.clv_status !== "no_close" &&
    r.clv_status !== null
  );
}

/**
 * Aggregate PaperTrailRow[] into one VenueStats per venue.
 * Result is sorted alphabetically by venue name.
 */
export function aggregateByVenue(rows: PaperTrailRow[]): VenueStats[] {
  const map = new Map<string, PaperTrailRow[]>();

  for (const row of rows) {
    const v = venueOf(row);
    const existing = map.get(v);
    if (existing) existing.push(row);
    else map.set(v, [row]);
  }

  const result: VenueStats[] = [];

  for (const [venue, venueRows] of map) {
    let openCount = 0;
    let settledCount = 0;
    let winCount = 0;
    let lossCount = 0;
    let pushCount = 0;
    let pendingCount = 0;

    let stakeSum = 0;
    let hasAnyStake = false;

    let probSum = 0;
    let probCount = 0;

    let clvSum = 0;
    let clvCount = 0;

    for (const row of venueRows) {
      const res: DerivedResult = deriveResult(row);

      // open / settled counts
      if (row.status === "open") openCount++;
      else settledCount++;

      // win / loss / push / pending
      if (res === "win") winCount++;
      else if (res === "loss") lossCount++;
      else if (res === "void") pushCount++;
      else pendingCount++;

      // units stake
      if (row.stake_units != null) {
        stakeSum += row.stake_units;
        hasAnyStake = true;
      }

      // model prob
      if (row.model_prob != null) {
        probSum += row.model_prob;
        probCount++;
      }

      // CLV -- only genuinely settled rows with a real close
      if (hasRealClv(row)) {
        clvSum += row.clv_pct as number;
        clvCount++;
      }
    }

    result.push({
      venue,
      total: venueRows.length,
      open: openCount,
      settled: settledCount,
      win: winCount,
      loss: lossCount,
      push: pushCount,
      pending: pendingCount,
      stake_units_total: hasAnyStake ? stakeSum : null,
      model_prob_mean: probCount > 0 ? probSum / probCount : null,
      clv_mean: clvCount > 0 ? clvSum / clvCount : null,
      clv_sample_n: clvCount,
    });
  }

  return result.sort((a, b) => a.venue.localeCompare(b.venue));
}
