"use client";

// PaperTrailSettled -- renders the REAL settled book from /api/paper/trail.
//
// PRIMARY paper record display: settled (win/loss/push) rows first,
// then open rows. Shows a win/loss/push tally strip at the top.
//
// HONESTY RAILS:
//   - UNITS only, NO $ or dollar-amount field anywhere.
//   - CLV shown when settled with a real/proxy close; "no-close" when absent.
//   - executed is ALWAYS false (paper-only).
//   - outcome = "win" | "loss" | "push" | "void" | null (pending).
//
// LOC note: TallyTile + deriveSettledTally + SettledTally live in
// settledTallyHelpers.tsx (split to keep each file under the 300-LOC rail).
// Open positions in non-settledOnly mode delegate to <OpenPositions> from
// OpenPositions.tsx to avoid duplicating that render logic.

import { useMemo } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { EMPTY_CELL, tierBadgeClass } from "@/lib/tokens";
import { Badge, Unavailable } from "@/components/p6/Primitives";
import { ClvInline } from "./ClvInline";
import { humanizeMatchup, describeBetShort } from "@/lib/betdesc";
import { TallyTile, deriveSettledTally } from "./settledTallyHelpers";
import { OpenPositions } from "./OpenPositions";
import type { PaperTrailRow } from "@/lib/p5api";

// Re-export for backward compat (tests import deriveSettledTally from here).
export { deriveSettledTally } from "./settledTallyHelpers";
export type { SettledTally } from "./settledTallyHelpers";

// ---------------------------------------------------------------------------
// Format helpers (no $ anywhere)
// ---------------------------------------------------------------------------

function fmtProb(p: number | null): string {
  return p != null ? `${(p * 100).toFixed(1)}%` : EMPTY_CELL;
}

function fmtDec(d: number | null): string {
  return d != null ? d.toFixed(2) : EMPTY_CELL;
}

function fmtUnits(u: number | null): string {
  return u != null ? `${u.toFixed(2)}u` : EMPTY_CELL;
}

/** Format model_ev (probability-space EV, not a $ amount). Sign-prefixed. */
function fmtEv(ev: number | null): string {
  if (ev == null) return EMPTY_CELL;
  const sign = ev >= 0 ? "+" : "";
  return `${sign}${(ev * 100).toFixed(1)}%`;
}

type ResultLabel = "win" | "loss" | "push" | "void" | "pending";
type ResultTone = "green" | "red" | "slate" | "amber";

function deriveResultLabel(r: PaperTrailRow): ResultLabel {
  if (r.status === "open" || !r.graded) return "pending";
  const o = (r.outcome || "").toLowerCase();
  if (o === "win") return "win";
  if (o === "loss") return "loss";
  if (o === "push") return "push";
  return "void";
}

const RESULT_TONE: Record<ResultLabel, ResultTone> = {
  win: "green",
  loss: "red",
  push: "slate",
  void: "slate",
  pending: "amber",
};

// ---------------------------------------------------------------------------
// SettledTableRow
// ---------------------------------------------------------------------------

function SettledTableRow({ row }: { row: PaperTrailRow }) {
  const res = deriveResultLabel(row);
  const isSettled = row.graded && row.status !== "open";
  return (
    <tr
      className={cn(
        "border-b border-slate-800/60 text-[12px] text-slate-300 transition-colors hover:bg-slate-800/30",
        !isSettled && "opacity-60",
      )}
      data-result={res}
    >
      <td className="px-2 py-1.5">
        <span className="font-medium">{humanizeMatchup(row.matchup || row.game_id)}</span>
        <span className="ml-1.5 font-mono text-[10px] text-slate-500">
          {row.sport?.toUpperCase()}
        </span>
        {row.prop_player ? (
          <span className="block font-mono text-[10px] text-sky-400/80" data-testid="settled-prop-selection">
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
      <td
        className="px-2 py-1.5 font-mono text-[11px] text-slate-400"
        data-testid="taken-book-cell"
      >
        {row.taken_book || EMPTY_CELL}
      </td>
      <td
        className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-400"
        data-testid="model-ev-cell"
      >
        {fmtEv(row.model_ev)}
      </td>
      <td className="px-2 py-1.5 text-right">
        <ClvInline row={row} />
      </td>
      <td
        className="px-2 py-1.5 font-mono text-[10px] text-slate-500"
        data-testid="clv-status-cell"
      >
        {row.clv_status ?? EMPTY_CELL}
      </td>
      <td className="px-2 py-1.5">
        <Badge tone={RESULT_TONE[res]}>
          <span data-testid="result-label">{res}</span>
        </Badge>
      </td>
      <td className="px-2 py-1.5 text-right font-mono tabular-nums text-slate-300">
        {fmtUnits(row.stake_units)}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// PaperTrailSettled -- main export
// ---------------------------------------------------------------------------

type Props = {
  rows: PaperTrailRow[];
  loading?: boolean;
  error?: string | null;
  /** If true, only show settled (graded) rows; open rows go to a secondary section. */
  settledOnly?: boolean;
};

export function PaperTrailSettled({ rows, loading, error, settledOnly }: Props) {
  const tally = useMemo(() => deriveSettledTally(rows), [rows]);

  const settledRows = useMemo(
    () => rows.filter((r) => r.graded && r.status !== "open"),
    [rows],
  );
  const displayRows = settledOnly ? settledRows : rows;

  if (loading && rows.length === 0) {
    return (
      <div aria-busy="true" aria-label="Loading settled paper trades" className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    );
  }

  if (error && rows.length === 0) return <Unavailable reason={error} />;

  return (
    <div className="flex flex-col gap-4">
      {/* Tally strip */}
      <div
        aria-label="Settled book tally"
        data-testid="settled-book-tally"
        className="grid grid-cols-3 gap-2 sm:grid-cols-6"
      >
        <TallyTile label="Settled" value={loading ? EMPTY_CELL : String(tally.nSettled)}
          testId="settled-tally-settled" loading={loading && rows.length === 0} />
        <TallyTile label="Win" value={loading ? EMPTY_CELL : String(tally.nWin)}
          testId="settled-tally-win"
          valueClass={tally.nWin > 0 ? "text-success" : "text-slate-100"}
          loading={loading && rows.length === 0} />
        <TallyTile label="Loss" value={loading ? EMPTY_CELL : String(tally.nLoss)}
          testId="settled-tally-loss"
          valueClass={tally.nLoss > 0 ? "text-danger" : "text-slate-100"}
          loading={loading && rows.length === 0} />
        <TallyTile label="Push" value={loading ? EMPTY_CELL : String(tally.nPush)}
          testId="settled-tally-push" loading={loading && rows.length === 0} />
        <TallyTile label="Open" value={loading ? EMPTY_CELL : String(tally.nOpen)}
          testId="settled-tally-open" loading={loading && rows.length === 0} />
        <TallyTile label="Void" value={loading ? EMPTY_CELL : String(tally.nVoid)}
          testId="settled-tally-void" loading={loading && rows.length === 0} />
      </div>

      {/* Settled records table -- primary section */}
      {settledRows.length === 0 && !loading ? (
        <div
          data-testid="no-settled-records"
          className="rounded-lg border border-slate-800 bg-bg-subtle/40 px-4 py-8 text-center text-sm text-slate-500"
        >
          No settled records yet. CLV populates as paper bets grade against the
          close. No edge is claimed.
        </div>
      ) : (
        <ScrollArea className="h-[480px] w-full rounded-lg border border-slate-800">
          <table
            className="min-w-full text-left"
            role="grid"
            aria-label="Settled paper book"
            data-testid="settled-records-table"
          >
            <caption className="sr-only">
              Settled paper book -- units and probability only, no dollar amounts.
              All trades are paper-only (executed=false).
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
                <th scope="col" className="px-2 py-2 text-right">Model EV</th>
                <th scope="col" className="px-2 py-2 text-right">CLV</th>
                <th scope="col" className="px-2 py-2">CLV status</th>
                <th scope="col" className="px-2 py-2">Result</th>
                <th scope="col" className="px-2 py-2 text-right">Units</th>
              </tr>
            </thead>
            <tbody>
              {(settledOnly ? displayRows : settledRows).map((r, i) => (
                <SettledTableRow key={`${r.game_id}-${r.market_type}-${r.side}-${i}`} row={r} />
              ))}
            </tbody>
          </table>
        </ScrollArea>
      )}

      {/* Open positions -- only shown when not settledOnly mode.
          Delegates to <OpenPositions> to avoid duplicating its render logic. */}
      {!settledOnly && <OpenPositions rows={rows} loading={loading} />}

      <p className="text-[11px] text-slate-600">
        Paper mode -- stakes are units (no $). CLV (better-number-than-close) is
        the only honest calibration yardstick. No edge is claimed.
      </p>
    </div>
  );
}
