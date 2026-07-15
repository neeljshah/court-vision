"use client";

// OpenPositions -- dedicated panel for open (ungraded) paper positions.
//
// Reads open rows from a PaperTrailRow[] slice (status="open" || !graded).
// HONESTY RAILS:
//   - UNITS only, NO $ anywhere.
//   - Large stake_units (>1.0) show a quarter-Kelly clarifier note.
//   - Paper mode -- executed is always false.
//   - Honest empty state when no open rows exist.
//   - Auto-refresh is handled at the page level via useLiveData; this component
//     is purely presentational (receives rows as a prop).

import { useMemo } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { EMPTY_CELL, tierBadgeClass } from "@/lib/tokens";
import { humanizeMatchup, describeBetShort } from "@/lib/betdesc";
import type { PaperTrailRow } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Format helpers (no $ anywhere)
// ---------------------------------------------------------------------------

function fmtProb(p: number | null): string {
  return p != null ? `${(p * 100).toFixed(1)}%` : EMPTY_CELL;
}

function fmtDec(d: number | null): string {
  return d != null ? d.toFixed(2) : EMPTY_CELL;
}

/** Format stake_units as "X.XXu". Also flags if >1.0 (quarter-Kelly note). */
function fmtUnits(u: number | null): string {
  return u != null ? `${u.toFixed(2)}u` : EMPTY_CELL;
}

const LARGE_UNITS_THRESHOLD = 1.0;

// ---------------------------------------------------------------------------
// OpenPositionRow -- one row in the open positions table
// ---------------------------------------------------------------------------

function OpenPositionRow({ row }: { row: PaperTrailRow }) {
  const isLargeStake =
    row.stake_units != null && row.stake_units > LARGE_UNITS_THRESHOLD;

  return (
    <tr
      className="border-b border-slate-800/60 text-[12px] text-slate-300 transition-colors hover:bg-slate-800/20"
      data-testid="open-position-row"
    >
      <td className="px-2 py-1.5">
        <span className="font-medium">{humanizeMatchup(row.matchup || row.game_id)}</span>
        <span className="ml-1.5 font-mono text-[10px] text-slate-500">
          {row.sport?.toUpperCase()}
        </span>
        {row.prop_player ? (
          <span className="block font-mono text-[10px] text-sky-400/80" data-testid="open-prop-selection">
            {row.prop_player}
            {row.prop_stat ? ` · ${row.prop_stat}` : ""}
          </span>
        ) : null}
      </td>
      <td className="px-2 py-1.5 font-mono text-[11px] text-slate-400">
        {row.market_type || EMPTY_CELL}
      </td>
      <td className="px-2 py-1.5 font-mono text-[11px] text-slate-400">
        {row.prop_side
          ? `${row.prop_side}${row.line != null ? ` ${row.line}` : ""}`
          : describeBetShort(row)}
      </td>
      <td className="px-2 py-1.5">
        {row.tier ? (
          <span
            className={cn(
              "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-mono uppercase",
              tierBadgeClass(row.tier),
            )}
          >
            {row.tier}
          </span>
        ) : (
          <span className="text-slate-600">{EMPTY_CELL}</span>
        )}
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
        {fmtProb(row.model_prob)}
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
        {fmtDec(row.taken_decimal)}
      </td>
      <td className="px-2 py-1.5 font-mono text-[10px] text-slate-400" data-testid="open-taken-book">
        {row.taken_book || EMPTY_CELL}
      </td>
      <td className="px-2 py-1.5 font-mono text-[11px] text-amber-400">
        pending
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums">
        <span
          className={cn(
            "tabular-nums",
            isLargeStake ? "text-amber-300" : "text-slate-300",
          )}
          data-testid="open-stake-units"
        >
          {fmtUnits(row.stake_units)}
        </span>
        {isLargeStake && (
          <span
            className="ml-1.5 font-mono text-[9px] text-amber-500/80"
            data-testid="quarter-kelly-clarifier"
            title="Quarter-Kelly sizing -- stake exceeds 1.0 unit. Units are not dollars."
          >
            qK
          </span>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// OpenPositions -- main export
// ---------------------------------------------------------------------------

export interface OpenPositionsProps {
  /** Full trail rows -- the component filters to open (status=open || !graded). */
  rows: PaperTrailRow[];
  loading?: boolean;
  error?: string | null;
}

export function OpenPositions({ rows, loading, error }: OpenPositionsProps) {
  const openRows = useMemo(
    () => rows.filter((r) => r.status === "open" || !r.graded),
    [rows],
  );

  const hasLargeStake = useMemo(
    () => openRows.some((r) => r.stake_units != null && r.stake_units > LARGE_UNITS_THRESHOLD),
    [openRows],
  );

  if (loading && rows.length === 0) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading open positions"
        className="space-y-2"
        data-testid="open-positions-loading"
      >
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (error && rows.length === 0) {
    return (
      <div
        data-testid="open-positions-error"
        className="rounded-lg border border-amber-900/40 bg-amber-950/20 px-4 py-3 text-sm text-amber-400"
      >
        {error}
      </div>
    );
  }

  if (openRows.length === 0 && !loading) {
    return (
      <div
        data-testid="open-positions-empty"
        className="rounded-lg border border-slate-800 bg-bg-subtle/40 px-4 py-6 text-center text-sm text-slate-500"
      >
        <p className="font-medium text-slate-400">No open positions right now.</p>
        <p className="mt-1 text-xs text-slate-600">
          Open bets appear here once the system places paper trades.
          Paper mode only -- no real money. No edge is claimed.
        </p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col gap-3"
      data-testid="open-positions-panel"
      aria-label="Open paper positions"
    >
      {/* Units convention clarifier */}
      <p className="text-[11px] text-slate-500">
        Stakes shown in <span className="font-semibold text-slate-300">UNITS</span> (not dollars).
        Quarter-Kelly sizing -- a stake can exceed 1.0u when the model is highly confident.
        {hasLargeStake && (
          <span
            className="ml-1 font-mono text-amber-400"
            data-testid="large-stake-unit-note"
          >
            {" "}qK = quarter-Kelly stake &gt;1.0u
          </span>
        )}
      </p>

      <ScrollArea className="h-[280px] w-full rounded-lg border border-slate-800">
        <table
          className="min-w-full text-left"
          role="grid"
          aria-label="Open paper positions"
          data-testid="open-positions-table"
        >
          <caption className="sr-only">
            Open paper positions -- pending grading. Units (no dollars).
            Executed is always false (paper only).
          </caption>
          <thead className="sticky top-0 z-10 bg-bg-panel text-[10px] uppercase tracking-wide text-slate-400">
            <tr className="border-b border-slate-800">
              <th scope="col" className="px-2 py-2">Matchup</th>
              <th scope="col" className="px-2 py-2">Market</th>
              <th scope="col" className="px-2 py-2">Side</th>
              <th scope="col" className="px-2 py-2">Tier</th>
              <th scope="col" className="px-2 py-2 text-right">Model P</th>
              <th scope="col" className="px-2 py-2 text-right">Entry</th>
              <th scope="col" className="px-2 py-2">Book</th>
              <th scope="col" className="px-2 py-2">Status</th>
              <th scope="col" className="px-2 py-2 text-right">Units</th>
            </tr>
          </thead>
          <tbody>
            {openRows.map((r, i) => (
              <OpenPositionRow key={`open-${r.game_id}-${r.market_type}-${i}`} row={r} />
            ))}
          </tbody>
        </table>
      </ScrollArea>

      <p className="text-[11px] text-slate-600">
        Paper mode -- stakes are units (no $). Real-money: DENY. No edge is claimed.
      </p>
    </div>
  );
}
