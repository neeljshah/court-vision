"use client";

// paperTradingHelpers.tsx -- shared helpers for the paper-trading page.
// Extracted to keep page.tsx under the 300 LOC/file rail.
//
// Exports: StatTile, deriveTally, DoneSummary, deriveDoneSummary,
//          TallySummary, toPaperTrailRows.
//
// HONESTY RAILS: units only; no $ edge; CLV = honest calibration yardstick.

import type { PaperTrail, PaperTrailRow, PmTrail, PmTrailRow, ClvScoreboard } from "@/lib/p5api";
import type { PaperTrailRow as PaperTrailRowType } from "@/lib/p5api";
import type { PnlSeries, PaperBankroll, Unavailable as UnavailableSentinel } from "@/lib/types";
import { api, isUnavailable } from "@/lib/p5api";
import { EMPTY_CELL } from "@/lib/tokens";

// ---------------------------------------------------------------------------
// Combined fetcher for the paper-trading page -- one useLiveData fetch pulls the
// trail + PM trail + CLV scoreboard + P&L equity series + bankroll in parallel.
// Trail is the PRIMARY feed: if it is unavailable the whole payload degrades to
// the Unavailable sentinel. Every secondary feed degrades to null independently.
// ---------------------------------------------------------------------------

export interface CombinedPayload {
  trail: PaperTrail | null;
  pmTrail: PmTrail | null;
  clv: ClvScoreboard | null;
  pnl: PnlSeries | null;
  bankroll: PaperBankroll | null;
}

export async function fetchPaperCombined(
  signal: AbortSignal,
): Promise<CombinedPayload | UnavailableSentinel> {
  const [t, pt, c, pnl, bank] = await Promise.all([
    // ponytail: 400 rows paints the page fast; raise if a view ever pages past it
    api.getPaperTrail({ limit: 400 }, signal),
    api.pmTrail(undefined, signal),
    api.getPaperClv(signal),
    api.getPaperPnlSeries(signal),
    api.getPaperBankroll(signal),
  ]);
  if (isUnavailable(t)) {
    return {
      status: "unavailable",
      reason: (t as { reason?: string }).reason ?? "unavailable",
    } as UnavailableSentinel;
  }
  return {
    trail: t as PaperTrail,
    pmTrail: isUnavailable(pt) ? null : (pt as PmTrail),
    clv: isUnavailable(c) ? null : (c as ClvScoreboard),
    pnl: isUnavailable(pnl) ? null : (pnl as PnlSeries),
    bankroll: isUnavailable(bank) ? null : (bank as PaperBankroll),
  };
}

// ---------------------------------------------------------------------------
// StatTile -- shared tile for tally + CLV. Neutral loading state; never red.
// ---------------------------------------------------------------------------

export function StatTile({
  label,
  value,
  loading,
  valueClass,
  testId,
}: {
  label: string;
  value: string;
  loading?: boolean;
  valueClass?: string;
  testId?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-bg-subtle px-3 py-3">
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      {loading ? (
        <div
          className="mt-1 h-7 w-14 animate-pulse rounded bg-slate-700/50"
          role="presentation"
          aria-busy="true"
          aria-label={`${label} loading`}
        />
      ) : (
        <div
          className={`mt-1 font-mono text-lg tabular-nums ${valueClass ?? "text-foreground"}`}
          data-testid={testId}
        >
          {value}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// deriveTally -- PM trade-level tally (open/settled/win/loss/push/units).
// ---------------------------------------------------------------------------

export interface TallySummary {
  nOpen: number;
  nSettled: number;
  nWin: number;
  nLoss: number;
  nPush: number;
  unitsStaked: number;
}

export function deriveTally(trades: PmTrailRow[]): TallySummary {
  let nOpen = 0, nSettled = 0, nWin = 0, nLoss = 0, nPush = 0, unitsStaked = 0;
  for (const t of trades) {
    if (t.result === null || t.result === undefined) {
      nOpen++;
    } else {
      nSettled++;
      if (t.result === "win") nWin++;
      else if (t.result === "loss") nLoss++;
      else if (t.result === "push") nPush++;
    }
    unitsStaked += t.units ?? 0;
  }
  return { nOpen, nSettled, nWin, nLoss, nPush, unitsStaked };
}

// ---------------------------------------------------------------------------
// deriveDoneSummary -- real trail-level done/settled summary.
// ---------------------------------------------------------------------------

export interface DoneSummary {
  nTotal: number;
  nSettled: number;
  nOpen: number;
  nWin: number;
  nLoss: number;
  nPush: number;
  nVoid: number;
  totalUnitsStaked: number;
}

export function deriveDoneSummary(rows: PaperTrailRow[]): DoneSummary {
  let nSettled = 0, nOpen = 0, nWin = 0, nLoss = 0, nPush = 0, nVoid = 0, totalUnitsStaked = 0;
  for (const r of rows) {
    if (r.status === "open" || !r.graded) {
      nOpen++;
    } else {
      nSettled++;
      const o = (r.outcome || "").toLowerCase();
      if (o === "win") nWin++;
      else if (o === "loss") nLoss++;
      else if (o === "push") nPush++;
      else nVoid++;
    }
    totalUnitsStaked += r.stake_units ?? 0;
  }
  return { nTotal: rows.length, nSettled, nOpen, nWin, nLoss, nPush, nVoid, totalUnitsStaked };
}

// ---------------------------------------------------------------------------
// toPaperTrailRows -- adapt PmTrailRow[] -> PaperTrailRow[] for PmTrailTable.
// ---------------------------------------------------------------------------

export function toPaperTrailRows(trades: PmTrailRow[]): PaperTrailRowType[] {
  return trades.map((t) => ({
    game_id: t.market_id,
    matchup: t.market_id,
    sport: t.venue,
    side: "home",
    market_type: t.market_id,
    line: null,
    taken_book: t.venue,
    taken_decimal: t.price_taken,
    model_prob: t.model_prob,
    model_ev: null,
    tier: t.tier,
    stake_units: t.units,
    status: t.result === null || t.result === undefined ? "open" : "settled",
    graded: t.result !== null && t.result !== undefined,
    outcome: t.result ?? null,
    clv_pct: t.clv,
    beat_close: t.clv != null ? t.clv > 0 : null,
    clv_is_proxy: t.clv_is_proxy,
    clv_status: t.clv_status,
    clv_unavailable: t.clv_status === "INSUFFICIENT_DATA" || t.clv === null,
    clv_note: t.clv_status,
    executed: false,
    ts: t.ts,
    settled_at: null,
  }));
}

// ---------------------------------------------------------------------------
// meanClvClass -- color class for the CLV mean tile.
// ---------------------------------------------------------------------------

export function meanClvClass(clv: ClvScoreboard | null): string {
  if (clv?.mean_clv_pct == null) return "text-foreground";
  if (clv.mean_clv_pct > 0) return "text-success";
  if (clv.mean_clv_pct < 0) return "text-danger";
  return "text-foreground";
}

// mergeVenueRows -- the row set the per-venue execution breakdown aggregates: the
// main paper trail (scope-filtered) UNION the separate Kalshi/Polymarket PM trail,
// deduped by a stable key so a bet recorded in both sources counts once. Surfaces
// sportsbooks + DFS prop books + Kalshi/Polymarket + in-game in one breakdown.
export function mergeVenueRows(
  trailRows: PaperTrailRowType[],
  pmRows: PaperTrailRowType[],
): PaperTrailRowType[] {
  const seen = new Set<string>();
  const merged: PaperTrailRowType[] = [];
  for (const r of [...trailRows, ...pmRows]) {
    const key = `${r.game_id}|${r.side}|${r.taken_book}|${r.taken_decimal}|${r.ts}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(r);
  }
  return merged;
}

// Re-export for callers that need to pass EMPTY_CELL without importing tokens.
export { EMPTY_CELL };
